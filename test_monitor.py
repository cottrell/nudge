import ast
import json
import os
import socket
import subprocess
import time

import pytest


AGENTS = ['claude', 'codex', 'copilot', 'gemini', 'grok', 'vibe', 'qwen', 'antigravity']
TEST_IDLE_SECS = 0.2


def _fixture_lines(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            try:
                value = ast.literal_eval(raw.strip())
            except Exception:
                continue
            if isinstance(value, str):
                yield value


def _load_jsonl(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return [json.loads(raw) for raw in f if raw.strip()]


def _sock_query(sock_path, command='status'):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(sock_path)
        client.sendall(command.encode())
        return json.loads(client.recv(65536))


def _wait_for_socket(sock_path):
    for _ in range(40):
        if os.path.exists(sock_path):
            return
        time.sleep(0.025)
    raise AssertionError(f'socket not created: {sock_path}')


def _wait_for_state(sock_path, expected, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _sock_query(sock_path)['state'] == expected:
            return
        time.sleep(0.025)
    assert _sock_query(sock_path)['state'] == expected


def _start_monitor(tmp_path, agent='claude', state_log=None, debug_path=None):
    sock_path = str(tmp_path / f'{agent}-{time.time_ns()}.sock')
    cmd = [
        './monitor-bin',
        '--agent', agent,
        '--socket', sock_path,
        '--idle-secs', str(TEST_IDLE_SECS),
    ]
    if state_log:
        cmd += ['--state-log', str(state_log)]
    if debug_path:
        cmd += ['--debug', str(debug_path)]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    _wait_for_socket(sock_path)
    return proc, sock_path


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()


def _write(proc, *lines):
    assert proc.stdin is not None
    for line in lines:
        proc.stdin.write(line + '\n')
    proc.stdin.flush()


def test_initial_state_is_unknown(tmp_path):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        assert _sock_query(sock_path) == {'state': 'unknown'}
    finally:
        _stop(proc)


@pytest.mark.parametrize('agent', AGENTS)
def test_any_agent_output_marks_working(tmp_path, agent):
    proc, sock_path = _start_monitor(tmp_path, agent)
    try:
        _write(proc, 'arbitrary terminal redraw')
        _wait_for_state(sock_path, 'working')
    finally:
        _stop(proc)


@pytest.mark.parametrize('line', [
    '❯ ',
    '-- INSERT -- ⏵⏵ bypass permissions on',
    '◐ medium · /effort',
    '✻ Crunched for 18s',
    'Error 429: Too Many Requests',
    '\x1b]0;✳ Claude Code\x07',
])
def test_content_does_not_change_activity_semantics(tmp_path, line):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        _write(proc, line)
        _wait_for_state(sock_path, 'working')
    finally:
        _stop(proc)


def test_quiet_timeout_marks_idle(tmp_path):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        _write(proc, 'output')
        _wait_for_state(sock_path, 'working')
        _wait_for_state(sock_path, 'idle')
    finally:
        _stop(proc)


def test_new_activity_returns_idle_to_working(tmp_path):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        _write(proc, 'first')
        _wait_for_state(sock_path, 'idle')
        _write(proc, 'second')
        _wait_for_state(sock_path, 'working')
    finally:
        _stop(proc)


def test_repeated_activity_extends_timeout(tmp_path):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        _write(proc, 'first')
        time.sleep(TEST_IDLE_SECS * 0.75)
        _write(proc, 'second')
        time.sleep(TEST_IDLE_SECS * 0.75)
        assert _sock_query(sock_path) == {'state': 'working'}
        _wait_for_state(sock_path, 'idle')
    finally:
        _stop(proc)


def test_blank_output_is_activity(tmp_path):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        _write(proc, '')
        _wait_for_state(sock_path, 'working')
        assert _sock_query(sock_path, 'tail') == {'line': ''}
    finally:
        _stop(proc)


def test_query_log_tail_and_unknown_command(tmp_path):
    proc, sock_path = _start_monitor(tmp_path)
    try:
        assert _sock_query(sock_path, 'tail') == {'line': None}
        _write(proc, 'line one', 'line two')
        _wait_for_state(sock_path, 'working')
        assert _sock_query(sock_path, 'log') == {'log': ['line one', 'line two']}
        assert _sock_query(sock_path, 'tail') == {'line': 'line two'}
        assert 'error' in _sock_query(sock_path, 'nonsense')
    finally:
        _stop(proc)


def test_cli_rejects_unknown_agent(tmp_path):
    proc = subprocess.run(
        ['./monitor-bin', '--agent', 'mistral', '--socket', str(tmp_path / 'bad.sock')],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert 'unknown agent type: mistral' in proc.stderr


@pytest.mark.parametrize('value', ['0', '-1', 'nan'])
def test_cli_rejects_invalid_idle_timeout(value):
    proc = subprocess.run(
        ['./monitor-bin', '--agent', 'claude', '--idle-secs', value],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert 'positive' in proc.stderr


def test_cli_help_lists_agents_and_idle_timeout():
    proc = subprocess.run(['./monitor-bin', '--help'], capture_output=True, text=True)
    assert proc.returncode == 0
    normalized = proc.stdout.replace('\n', ' ')
    assert 'claude, codex, copilot, gemini, grok, vibe, qwen, antigravity' in normalized
    assert 'idle-secs' in normalized


def test_fixture_replay_becomes_idle_after_quiet(tmp_path):
    checked = 0
    for agent in AGENTS:
        path = os.path.join('fixtures', f'{agent}_capture.txt')
        lines = list(_fixture_lines(path)) if os.path.exists(path) else []
        if not lines:
            continue
        checked += 1
        proc, sock_path = _start_monitor(tmp_path, agent)
        try:
            _write(proc, *lines)
            if agent == 'grok':
                _wait_for_state(sock_path, 'idle')
            else:
                _wait_for_state(sock_path, 'working')
                _wait_for_state(sock_path, 'idle')
        finally:
            _stop(proc)
    if checked == 0:
        pytest.skip('no capture fixtures found')


def test_state_log_records_activity_and_timeout(tmp_path):
    state_log = tmp_path / 'state.jsonl'
    proc, sock_path = _start_monitor(tmp_path, state_log=state_log)
    try:
        _write(proc, 'status bar')
        _wait_for_state(sock_path, 'idle')
        rows = _load_jsonl(state_log)
        assert [row['state'] for row in rows] == ['unknown', 'working', 'idle']
        assert rows[1]['line'] == 'status bar'
        assert 'line' not in rows[2]
    finally:
        _stop(proc)


def test_debug_writes_raw_lines(tmp_path):
    debug_path = tmp_path / 'debug.txt'
    proc, _ = _start_monitor(tmp_path, debug_path=debug_path)
    try:
        _write(proc, 'hello', '> ')
        time.sleep(0.05)
    finally:
        _stop(proc)
    assert debug_path.read_text().splitlines() == ["'hello'", "'> '"]
