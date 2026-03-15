import json
import ast
import os
import socket
import subprocess
import threading
import time

import pytest

from monitor import Monitor
from monitor import _IDLE_HOLDOFF_AGENTS

FIXTURE_AGENTS = ['claude', 'codex', 'copilot', 'gemini', 'qwen']


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


def _sock_status(sock_path):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(sock_path)
    c.sendall(b'status')
    resp = json.loads(c.recv(1024))
    c.close()
    return resp['state']


def _expected_final_state(agent):
    path = os.path.join('fixtures', f'{agent}_transitions.jsonl')
    if not os.path.exists(path):
        raise AssertionError(f'missing transition fixture: {path}')
    last = None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get('state'), str):
                last = obj['state']
    return last


def _load_jsonl(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return [json.loads(raw) for raw in f if raw.strip()]


# --- classify ---

def test_initial_state_is_unknown():
    m = Monitor('claude')
    assert m.state == 'unknown'

def test_classify_claude_working_braille():
    m = Monitor('claude')
    assert m.classify('⠙ Thinking…') == 'working'

def test_classify_claude_working_spinner():
    # real raw: cursor-forward sequences stripped, no space between ✻ and verb
    m = Monitor('claude')
    assert m.classify('\x1b[38;2;153;153;153m✻\x1b[1CSautéed\x1b[1Cfor\x1b[1C3m\x1b[1C24s\x1b[39m') == 'working'

def test_classify_claude_idle_prompt():
    m = Monitor('claude')
    assert m.classify('> ') == 'idle'

def test_classify_claude_idle_insert_mode():
    # real prompt line after ANSI stripping
    m = Monitor('claude')
    assert m.classify('\u276f\u00a0 ') == 'idle'

def test_classify_claude_idle_chevron():
    m = Monitor('claude')
    assert m.classify('❯ ') == 'idle'

def test_classify_claude_insert_redraw_is_not_idle():
    m = Monitor('claude')
    assert m.classify('--INSERT--⏵⏵bypasspermissionson (shift+tabtocycle)') is None

def test_classify_claude_insert_redraw_with_effort_is_ignored():
    m = Monitor('claude')
    assert m.classify('--INSERT--⏵⏵bypasspermissionson (shift+tabtocycle)◐medium·/effo…') is None

def test_classify_claude_final_response_with_prompt_is_idle():
    m = Monitor('claude')
    assert m.classify('\x1b[?2026l\x1b[?2026h\r\x1b[7A\x1b[38;2;255;255;255m●\x1b[1C\x1b[39mHello!    \r\x1b[3B❯\u00a0') == 'idle'

def test_classify_rate_limited_overloaded():
    m = Monitor('claude')
    assert m.classify('overloaded_error') == 'rate_limited'

def test_classify_rate_limited_429():
    m = Monitor('claude')
    assert m.classify('Error 429: Too Many Requests') == 'rate_limited'

def test_classify_rate_limited_529():
    m = Monitor('claude')
    assert m.classify('529 server error') == 'rate_limited'

def test_classify_rate_limited_retry():
    m = Monitor('claude')
    assert m.classify('Retrying in 5 seconds') == 'rate_limited'

def test_classify_error():
    m = Monitor('claude')
    assert m.classify('API Error: authentication_error') == 'error'

def test_classify_gemini_working():
    m = Monitor('gemini')
    assert m.classify('⠋ Thinking ... (esc to cancel, 5s)') == 'working'

def test_classify_gemini_idle():
    m = Monitor('gemini')
    assert m.classify('> ') == 'idle'

def test_classify_gemini_idle_real():
    m = Monitor('gemini')
    assert m.classify(' >   Type your message or @path/to/file') == 'idle'

def test_classify_gemini_idle_shortcuts():
    m = Monitor('gemini')
    assert m.classify('? for shortcuts') == 'idle'

def test_classify_gemini_rate_limited():
    m = Monitor('gemini')
    assert m.classify('API Error 429: Quota exceeded') == 'rate_limited'

def test_classify_gemini_error():
    m = Monitor('gemini')
    assert m.classify('✕ Error: something went wrong') == 'error'

def test_classify_vibe_idle():
    m = Monitor('vibe')
    assert m.classify('> ') == 'idle'

def test_classify_vibe_boxed_idle():
    m = Monitor('vibe')
    assert m.classify('│ >                                                                                                                                 │') == 'idle'

def test_classify_vibe_logo_is_not_working():
    m = Monitor('vibe')
    assert m.classify('  ⡠⣒⠄  ⡔⢄⠔⡄  Mistral Vibe v2.4.2 · devstral-2') is None

def test_classify_vibe_status_banner_is_not_working():
    m = Monitor('vibe')
    assert m.classify('⢸⠸⣀⡔⢉⠱⣃⡠⣀⡣   3 models · 1 MCP server · 0 skills') is None

def test_classify_qwen_working_braille():
    m = Monitor('qwen')
    assert m.classify('⠙ Thinking...') == 'working'

def test_classify_qwen_working_braille_variant():
    m = Monitor('qwen')
    assert m.classify('⠋ Processing...') == 'working'

def test_classify_qwen_idle():
    m = Monitor('qwen')
    assert m.classify('> ') == 'idle'

def test_classify_qwen_idle_real():
    m = Monitor('qwen')
    assert m.classify('>   Type your message or @path/to/file') == 'idle'

def test_classify_qwen_idle_shortcuts():
    m = Monitor('qwen')
    assert m.classify('? for shortcuts') == 'idle'

def test_classify_qwen_rate_limited():
    m = Monitor('qwen')
    assert m.classify('Error 429: Too Many Requests') == 'rate_limited'

def test_classify_qwen_error():
    m = Monitor('qwen')
    assert m.classify('Error: something went wrong') == 'error'

def test_classify_copilot_idle():
    m = Monitor('copilot')
    assert m.classify('› ') == 'idle'

def test_classify_copilot_idle_prompt_help():
    m = Monitor('copilot')
    assert m.classify('❯  Type @ to mention files, # for issues/PRs, / for commands, or ? for shortcuts') == 'idle'

def test_classify_copilot_working():
    m = Monitor('copilot')
    assert m.classify('esc to interrupt') == 'working'

def test_classify_codex_idle_prompt():
    m = Monitor('codex')
    assert m.classify('$ ') == 'idle'

def test_classify_codex_idle_reply():
    m = Monitor('codex')
    assert m.classify('› Reply with exactly: OK') == 'idle'

def test_classify_codex_idle_ready_screen():
    m = Monitor('codex')
    assert m.classify('› Summarize recent commits ? for shortcuts 100% context left') == 'idle'

def test_classify_codex_working():
    m = Monitor('codex')
    assert m.classify('thinking') == 'working'

def test_classify_codex_working_real():
    m = Monitor('codex')
    assert m.classify('• Working (0s • esc to interrupt)') == 'working'

def test_classify_codex_rate_limit_tip_is_not_rate_limited():
    m = Monitor('codex')
    assert m.classify('Tip: New 2x rate limits until April 2nd.') is None

def test_classify_unrecognised_line_returns_none():
    m = Monitor('claude')
    assert m.classify('some random output') is None

def test_classify_unknown_agent_type():
    m = Monitor('unknown_agent')
    assert m.classify('Thinking...') is None


# --- ingest / state ---

def test_ingest_updates_state():
    m = Monitor('claude')
    m.ingest('⠙ Thinking...')
    assert m.state == 'working'

def test_ingest_appends_to_log():
    m = Monitor('claude')
    m.ingest('hello world')
    assert 'hello world' in m.log

def test_state_holds_on_unclassified_line():
    m = Monitor('claude')
    m.ingest('⠙ Thinking...')
    m.ingest('some unrecognised line')
    assert m.state == 'working'

def test_state_transitions():
    m = Monitor('claude')
    m.ingest('⠙ Thinking...')
    assert m.state == 'working'
    m.ingest('Claude AI is currently overloaded')
    assert m.state == 'rate_limited'

def test_idle_holdoff_prevents_spinner_redraw_flap():
    m = Monitor('gemini')
    m.ingest('⠙ Thinking ... (esc to cancel, 5s)')
    assert m.state == 'working'
    m.ingest('*   Type your message or @path/to/file')
    assert m.state == 'working'

def test_copilot_idle_holdoff_prevents_spinner_redraw_flap():
    m = Monitor('copilot')
    m.ingest('● Thinking (Esc to cancel)')
    assert m.state == 'working'
    m.ingest('❯  Type @ to mention files, # for issues/PRs, / for commands, or ? for')
    assert m.state == 'working'

def test_codex_idle_holdoff_prevents_prompt_redraw_flap():
    m = Monitor('codex')
    m.ingest('thinking')
    assert m.state == 'working'
    m.ingest('› Find and fix a bug in @filename')
    assert m.state == 'working'

def test_qwen_idle_holdoff_prevents_spinner_redraw_flap():
    m = Monitor('qwen')
    m.ingest('⠙ Aligning the stars for optimal response... (esc to cancel, 4s)')
    assert m.state == 'working'
    m.ingest('>   Type your message or @path/to/file')
    assert m.state == 'working'

def test_vibe_idle_holdoff_prevents_prompt_redraw_flap():
    m = Monitor('vibe')
    m.ingest('⠉⠁ Generating… (0s esc to interrupt)')
    assert m.state == 'working'
    m.ingest('>')
    assert m.state == 'working'

def test_codex_quiet_working_falls_back_to_idle():
    m = Monitor('codex')
    m.ingest('• Starting MCP servers (0/2): backlog, pal (0s • esc to interrupt)')
    assert m.state == 'working'
    time.sleep(2.2)
    with m._lock:
        m._refresh_state_locked()
    assert m.state == 'idle'

def test_state_log_records_init_and_changes(tmp_path):
    path = tmp_path / 'state.jsonl'
    m = Monitor('claude', state_log=str(path))
    m.ingest('⠙ Thinking...')
    m.ingest('> ')
    rows = _load_jsonl(path)
    assert [row['event'] for row in rows] == ['init', 'change', 'change']
    assert [row['state'] for row in rows] == ['unknown', 'working', 'idle']
    assert rows[1]['line'] == '⠙ Thinking...'
    assert rows[2]['line'] == '>'

def test_query_does_not_promote_pending_idle(tmp_path):
    path = tmp_path / 'state-query.jsonl'
    m = Monitor('gemini', state_log=str(path))
    m.ingest('⠙ Thinking ... (esc to cancel, 5s)')
    m.ingest('*   Type your message or @path/to/file')
    before = _load_jsonl(path)
    assert [row['state'] for row in before] == ['unknown', 'working']
    assert m.query('status') == {'state': 'working'}
    after = _load_jsonl(path)
    assert after == before


# --- query ---

def test_query_status():
    m = Monitor('claude')
    m.ingest('⠙ Thinking...')
    assert m.query('status') == {'state': 'working'}

def test_query_log():
    m = Monitor('claude')
    m.ingest('line one')
    m.ingest('line two')
    result = m.query('log')
    assert 'line one' in result['log']
    assert 'line two' in result['log']

def test_query_tail():
    m = Monitor('claude')
    m.ingest('line one')
    m.ingest('line two')
    assert m.query('tail') == {'line': 'line two'}

def test_query_unknown_command():
    m = Monitor('claude')
    result = m.query('nonsense')
    assert 'error' in result


# --- socket ---

@pytest.fixture
def sock_path(tmp_path):
    return str(tmp_path / 'test.sock')

def test_socket_status(sock_path):
    m = Monitor('claude', socket_path=sock_path)
    t = threading.Thread(target=m.serve, daemon=True)
    t.start()
    time.sleep(0.05)

    m.ingest('⠙ Thinking...')

    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(sock_path)
    c.sendall(b'status')
    resp = json.loads(c.recv(1024))
    c.close()

    assert resp == {'state': 'working'}

def test_socket_multiple_queries(sock_path):
    m = Monitor('claude', socket_path=sock_path)
    t = threading.Thread(target=m.serve, daemon=True)
    t.start()
    time.sleep(0.05)

    m.ingest('⠙ Thinking...')

    for _ in range(3):
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(sock_path)
        c.sendall(b'status')
        resp = json.loads(c.recv(1024))
        c.close()
        assert resp['state'] == 'working'


def test_fixture_replay_classifies_for_python():
    checked = 0
    for agent in FIXTURE_AGENTS:
        path = os.path.join('fixtures', f'{agent}_capture.txt')
        if not os.path.exists(path):
            continue
        checked += 1
        m = Monitor(agent)
        seen = set()
        for line in _fixture_lines(path):
            m.ingest(line)
            seen.add(m.state)
        assert any(state != 'unknown' for state in seen), f'no classified state in {path}'
        if agent in _IDLE_HOLDOFF_AGENTS:
            time.sleep(2.25)
            with m._lock:
                m._refresh_state_locked()
        expected = _expected_final_state(agent)
        assert m.state == expected, f'python final state mismatch for {agent}'
    if checked == 0:
        pytest.skip('no capture fixtures found')


def test_fixture_replay_c_matches_python_final_state(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    checked = 0
    for agent in FIXTURE_AGENTS:
        path = os.path.join('fixtures', f'{agent}_capture.txt')
        if not os.path.exists(path):
            continue
        lines = list(_fixture_lines(path))
        if not lines:
            continue
        checked += 1

        py_monitor = Monitor(agent)
        for line in lines:
            py_monitor.ingest(line)
        if agent in _IDLE_HOLDOFF_AGENTS:
            time.sleep(2.25)
            with py_monitor._lock:
                py_monitor._refresh_state_locked()

        sock_path = str(tmp_path / f'{agent}.sock')
        proc = subprocess.Popen(
            ['./monitor-bin', '--agent', agent, '--socket', sock_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            assert proc.stdin is not None
            for line in lines:
                proc.stdin.write(line + '\n')
            proc.stdin.flush()

            for _ in range(20):
                if os.path.exists(sock_path):
                    break
                time.sleep(0.05)

            time.sleep(2.4 if agent in _IDLE_HOLDOFF_AGENTS else 0.1)
            c_state = _sock_status(sock_path)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()

        expected = _expected_final_state(agent)
        assert c_state == expected, f'c final state mismatch for {agent}'
        assert c_state == py_monitor.state

    if checked == 0:
        pytest.skip('no capture fixtures found')


def test_c_state_log_records_init_and_changes(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-state.sock')
    state_log = str(tmp_path / 'c-state.jsonl')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'claude', '--socket', sock_path, '--state-log', state_log],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('⠙ Thinking...\n')
        proc.stdin.write('> \n')
        proc.stdin.flush()
        proc.stdin.close()
        proc.wait(timeout=1)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()

    rows = _load_jsonl(state_log)
    assert [row['event'] for row in rows] == ['init', 'change', 'change']
    assert [row['state'] for row in rows] == ['unknown', 'working', 'idle']


def test_c_debug_writes_raw_lines(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-debug.sock')
    debug_path = str(tmp_path / 'c-debug.txt')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'claude', '--socket', sock_path, '--debug', debug_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('hello\n')
        proc.stdin.write('> \n')
        proc.stdin.flush()
        time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

    with open(debug_path, 'r', encoding='utf-8', errors='replace') as f:
        rows = [raw.rstrip('\n') for raw in f]
    assert rows == ["'hello'", "'> '"]


def test_c_idle_holdoff_prevents_spinner_redraw_flap(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-holdoff.sock')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'gemini', '--socket', sock_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('⠙ Thinking ... (esc to cancel, 5s)\n')
        proc.stdin.write('*   Type your message or @path/to/file\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        assert _sock_status(sock_path) == 'working'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

def test_c_copilot_idle_holdoff_prevents_spinner_redraw_flap(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-copilot-holdoff.sock')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'copilot', '--socket', sock_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('● Thinking (Esc to cancel)\n')
        proc.stdin.write('❯  Type @ to mention files, # for issues/PRs, / for commands, or ? for\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        assert _sock_status(sock_path) == 'working'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

def test_c_codex_idle_holdoff_prevents_prompt_redraw_flap(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-codex-holdoff.sock')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'codex', '--socket', sock_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('thinking\n')
        proc.stdin.write('› Find and fix a bug in @filename\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        assert _sock_status(sock_path) == 'working'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

def test_c_qwen_idle_holdoff_prevents_spinner_redraw_flap(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-qwen-holdoff.sock')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'qwen', '--socket', sock_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('⠙ Aligning the stars for optimal response... (esc to cancel, 4s)\n')
        proc.stdin.write('>   Type your message or @path/to/file\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        assert _sock_status(sock_path) == 'working'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

def test_c_vibe_idle_holdoff_prevents_prompt_redraw_flap(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-vibe-holdoff.sock')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'vibe', '--socket', sock_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('⠉⠁ Generating… (0s esc to interrupt)\n')
        proc.stdin.write('>\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        assert _sock_status(sock_path) == 'working'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

def test_c_codex_quiet_working_falls_back_to_idle(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-codex-quiet.sock')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'codex', '--socket', sock_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('• Starting MCP servers (0/2): backlog, pal (0s • esc to interrupt)\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        assert _sock_status(sock_path) == 'working'
        deadline = time.time() + 4.0
        while time.time() < deadline:
            if _sock_status(sock_path) == 'idle':
                break
            time.sleep(0.1)
        assert _sock_status(sock_path) == 'idle'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_c_query_does_not_promote_pending_idle(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    sock_path = str(tmp_path / 'c-query.sock')
    state_log = str(tmp_path / 'c-query.jsonl')
    proc = subprocess.Popen(
        ['./monitor-bin', '--agent', 'gemini', '--socket', sock_path, '--state-log', state_log],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write('⠙ Thinking ... (esc to cancel, 5s)\n')
        proc.stdin.write('*   Type your message or @path/to/file\n')
        proc.stdin.flush()
        for _ in range(20):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        time.sleep(0.1)
        before = _load_jsonl(state_log)
        assert [row['state'] for row in before] == ['unknown', 'working']
        assert _sock_status(sock_path) == 'working'
        after = _load_jsonl(state_log)
        assert after == before
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
