import ast
import json
import os
import socket
import subprocess
import threading
import time

import pytest

from monitor import Monitor


FIXTURE_AGENTS = ['claude', 'codex', 'copilot', 'gemini', 'grok', 'vibe', 'qwen', 'antigravity']
TEST_IDLE_SECS = 0.2


def _fixture_lines(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                value = ast.literal_eval(raw)
            except Exception:
                continue
            if isinstance(value, str):
                yield value


def _load_jsonl(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return [json.loads(raw) for raw in f if raw.strip()]


def _sock_query(sock_path, command='status'):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(sock_path)
    c.sendall(command.encode())
    resp = json.loads(c.recv(65536))
    c.close()
    return resp


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


def _start_c_monitor(tmp_path, agent='claude', state_log=None, debug_path=None):
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


def test_initial_state_is_unknown():
    assert Monitor('claude').state == 'unknown'


@pytest.mark.parametrize('agent', FIXTURE_AGENTS)
def test_any_agent_output_marks_working(agent):
    m = Monitor(agent, idle_secs=TEST_IDLE_SECS)
    m.ingest('arbitrary terminal redraw')
    assert m.state == 'working'


@pytest.mark.parametrize('line', [
    '❯ ',
    '-- INSERT -- ⏵⏵ bypass permissions on',
    '◐ medium · /effort',
    '✻ Crunched for 18s',
    'Error 429: Too Many Requests',
    '\x1b]0;✳ Claude Code\x07',
])
def test_content_does_not_change_activity_semantics(line):
    m = Monitor('claude', idle_secs=TEST_IDLE_SECS)
    m.ingest(line)
    assert m.state == 'working'


def test_quiet_timeout_marks_idle_without_sleep():
    m = Monitor('claude', idle_secs=10)
    m.ingest('output')
    with m._lock:
        assert m._last_ingest_at is not None
        m._refresh_state_locked(now=m._last_ingest_at + 10.01)
    assert m.state == 'idle'


def test_activity_before_timeout_keeps_working():
    m = Monitor('claude', idle_secs=10)
    m.ingest('output')
    with m._lock:
        assert m._last_ingest_at is not None
        m._refresh_state_locked(now=m._last_ingest_at + 9.99)
    assert m.state == 'working'


def test_new_activity_returns_idle_monitor_to_working():
    m = Monitor('claude', idle_secs=1)
    m.ingest('first')
    with m._lock:
        assert m._last_ingest_at is not None
        m._refresh_state_locked(now=m._last_ingest_at + 1.1)
    assert m.state == 'idle'
    m.ingest('second')
    assert m.state == 'working'


def test_repeated_activity_extends_deadline():
    m = Monitor('claude', idle_secs=10)
    m.ingest('first')
    first = m._last_ingest_at
    time.sleep(0.01)
    m.ingest('second')
    second = m._last_ingest_at
    assert first is not None and second is not None and second > first
    with m._lock:
        m._refresh_state_locked(now=first + 10.01)
    assert m.state == 'working'


def test_blank_output_is_activity():
    m = Monitor('claude', idle_secs=TEST_IDLE_SECS)
    m.ingest('\n')
    assert m.state == 'working'
    assert m.query('tail') == {'line': ''}


def test_ingest_appends_to_log():
    m = Monitor('claude')
    m.ingest('hello world')
    assert list(m.log) == ['hello world']


def test_state_log_records_activity_and_timeout(tmp_path):
    path = tmp_path / 'state.jsonl'
    m = Monitor('claude', state_log=str(path), idle_secs=1)
    m.ingest('status bar')
    with m._lock:
        assert m._last_ingest_at is not None
        m._refresh_state_locked(now=m._last_ingest_at + 1.1)
    rows = _load_jsonl(path)
    assert [row['state'] for row in rows] == ['unknown', 'working', 'idle']
    assert rows[1]['line'] == 'status bar'
    assert 'line' not in rows[2]


def test_query_status_does_not_change_state():
    m = Monitor('claude', idle_secs=1)
    m.ingest('output')
    assert m.query('status') == {'state': 'working'}
    assert m.state == 'working'


def test_query_log():
    m = Monitor('claude')
    m.ingest('line one')
    m.ingest('line two')
    assert m.query('log') == {'log': ['line one', 'line two']}


def test_query_raw():
    m = Monitor('claude')
    m.ingest('line  ')
    assert m.query('raw') == {'raw': ['line  ']}


def test_query_tail():
    m = Monitor('claude')
    assert m.query('tail') == {'line': None}
    m.ingest('line one')
    assert m.query('tail') == {'line': 'line one'}


def test_query_unknown_command():
    assert 'error' in Monitor('claude').query('nonsense')


def test_unknown_agent_type():
    with pytest.raises(ValueError, match='unknown agent type: unknown_agent'):
        Monitor('unknown_agent')


@pytest.mark.parametrize('idle_secs', [0, -1, float('nan')])
def test_python_rejects_nonpositive_idle_timeout(idle_secs):
    with pytest.raises(ValueError, match='idle_secs must be positive'):
        Monitor('claude', idle_secs=idle_secs)


def test_python_cli_rejects_unknown_agent(tmp_path):
    proc = subprocess.run(
        ['python', 'monitor.py', '--agent', 'mistral', '--socket', str(tmp_path / 'bad.sock')],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert 'unknown agent type: mistral' in proc.stderr


def test_c_cli_rejects_unknown_agent(tmp_path):
    proc = subprocess.run(
        ['./monitor-bin', '--agent', 'mistral', '--socket', str(tmp_path / 'bad.sock')],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert 'unknown agent type: mistral' in proc.stderr


@pytest.mark.parametrize('command', [
    ['python', 'monitor.py', '--agent', 'claude', '--idle-secs', '0'],
    ['./monitor-bin', '--agent', 'claude', '--idle-secs', '0'],
    ['python', 'monitor.py', '--agent', 'claude', '--idle-secs', 'nan'],
    ['./monitor-bin', '--agent', 'claude', '--idle-secs', 'nan'],
])
def test_cli_rejects_nonpositive_idle_timeout(command):
    proc = subprocess.run(command, capture_output=True, text=True)
    assert proc.returncode == 2
    assert 'positive' in proc.stderr


@pytest.mark.parametrize('command', [
    ['python', 'monitor.py', '--help'],
    ['./monitor-bin', '--help'],
])
def test_cli_help_lists_agents_and_idle_timeout(command):
    proc = subprocess.run(command, capture_output=True, text=True)
    assert proc.returncode == 0
    normalized = proc.stdout.replace('\n', ' ')
    assert 'claude, codex, copilot, gemini, grok, vibe, qwen, antigravity' in normalized
    assert 'idle-secs' in normalized


def test_socket_status(tmp_path):
    sock_path = str(tmp_path / 'python.sock')
    m = Monitor('claude', socket_path=sock_path, idle_secs=TEST_IDLE_SECS)
    threading.Thread(target=m.serve, daemon=True).start()
    _wait_for_socket(sock_path)
    m.ingest('anything')
    assert _sock_query(sock_path) == {'state': 'working'}


def test_socket_multiple_queries(tmp_path):
    sock_path = str(tmp_path / 'python-multi.sock')
    m = Monitor('claude', socket_path=sock_path, idle_secs=TEST_IDLE_SECS)
    threading.Thread(target=m.serve, daemon=True).start()
    _wait_for_socket(sock_path)
    m.ingest('anything')
    for _ in range(3):
        assert _sock_query(sock_path) == {'state': 'working'}


def test_fixture_replay_python_becomes_idle_after_quiet():
    checked = 0
    for agent in FIXTURE_AGENTS:
        path = os.path.join('fixtures', f'{agent}_capture.txt')
        if not os.path.exists(path):
            continue
        checked += 1
        m = Monitor(agent, idle_secs=1)
        for line in _fixture_lines(path):
            m.ingest(line)
            assert m.state == 'working'
        with m._lock:
            assert m._last_ingest_at is not None
            m._refresh_state_locked(now=m._last_ingest_at + 1.1)
        assert m.state == 'idle'
    if checked == 0:
        pytest.skip('no capture fixtures found')


def test_fixture_replay_c_matches_python(tmp_path):
    checked = 0
    for agent in FIXTURE_AGENTS:
        path = os.path.join('fixtures', f'{agent}_capture.txt')
        lines = list(_fixture_lines(path)) if os.path.exists(path) else []
        if not lines:
            continue
        checked += 1
        py_monitor = Monitor(agent, idle_secs=TEST_IDLE_SECS)
        for line in lines:
            py_monitor.ingest(line)
        assert py_monitor.state == 'working'

        proc, sock_path = _start_c_monitor(tmp_path, agent)
        try:
            assert proc.stdin is not None
            for line in lines:
                proc.stdin.write(line + '\n')
            proc.stdin.flush()
            _wait_for_state(sock_path, 'working')
            _wait_for_state(sock_path, 'idle')
        finally:
            _stop(proc)

        with py_monitor._lock:
            assert py_monitor._last_ingest_at is not None
            py_monitor._refresh_state_locked(now=py_monitor._last_ingest_at + TEST_IDLE_SECS + 0.01)
        assert py_monitor.state == 'idle'
    if checked == 0:
        pytest.skip('no capture fixtures found')


def test_c_state_log_records_activity_and_timeout(tmp_path):
    state_log = tmp_path / 'c-state.jsonl'
    proc, sock_path = _start_c_monitor(tmp_path, state_log=state_log)
    try:
        assert proc.stdin is not None
        proc.stdin.write('status bar\n')
        proc.stdin.flush()
        _wait_for_state(sock_path, 'idle')
        rows = _load_jsonl(state_log)
        assert [row['state'] for row in rows] == ['unknown', 'working', 'idle']
        assert rows[1]['line'] == 'status bar'
        assert 'line' not in rows[2]
    finally:
        _stop(proc)


def test_c_debug_writes_raw_lines(tmp_path):
    debug_path = tmp_path / 'c-debug.txt'
    proc, _ = _start_c_monitor(tmp_path, debug_path=debug_path)
    try:
        assert proc.stdin is not None
        proc.stdin.write('hello\n')
        proc.stdin.write('> \n')
        proc.stdin.flush()
        time.sleep(0.05)
    finally:
        _stop(proc)
    assert debug_path.read_text().splitlines() == ["'hello'", "'> '"]


def test_c_repeated_activity_extends_timeout(tmp_path):
    proc, sock_path = _start_c_monitor(tmp_path)
    try:
        assert proc.stdin is not None
        proc.stdin.write('first\n')
        proc.stdin.flush()
        time.sleep(TEST_IDLE_SECS * 0.75)
        proc.stdin.write('second\n')
        proc.stdin.flush()
        time.sleep(TEST_IDLE_SECS * 0.75)
        assert _sock_query(sock_path)['state'] == 'working'
        _wait_for_state(sock_path, 'idle')
    finally:
        _stop(proc)


def test_c_idle_returns_to_working_on_new_output(tmp_path):
    proc, sock_path = _start_c_monitor(tmp_path)
    try:
        assert proc.stdin is not None
        proc.stdin.write('first\n')
        proc.stdin.flush()
        _wait_for_state(sock_path, 'idle')
        proc.stdin.write('second\n')
        proc.stdin.flush()
        _wait_for_state(sock_path, 'working')
    finally:
        _stop(proc)
