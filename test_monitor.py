import json
import ast
import os
import socket
import subprocess
import threading
import time

import pytest

from monitor import Monitor


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
    path = os.path.join('fixtures', f'{agent}_states.jsonl')
    if not os.path.exists(path):
        return None
    last = None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if isinstance(obj, dict):
                st = obj.get('status')
                if isinstance(st, dict) and isinstance(st.get('state'), str):
                    last = st['state']
    return last


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
    # real raw line: cursor-forward stripped, ❯ triggers idle
    m = Monitor('claude')
    assert m.classify('\u276f\u00a0 ') == 'idle'

def test_classify_claude_idle_chevron():
    m = Monitor('claude')
    assert m.classify('❯ ') == 'idle'

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
    for agent in ['claude', 'codex', 'gemini', 'vibe']:
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
        expected = _expected_final_state(agent)
        if expected:
            assert m.state == expected, f'python final state mismatch for {agent}'
    if checked == 0:
        pytest.skip('no capture fixtures found')


def test_fixture_replay_c_matches_python_final_state(tmp_path):
    if not os.path.exists('./monitor-bin'):
        pytest.skip('monitor-bin not built')

    checked = 0
    for agent in ['claude', 'codex', 'gemini', 'vibe']:
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

            # Give C time to ingest all lines before querying
            time.sleep(0.1)
            c_state = _sock_status(sock_path)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()

        expected = _expected_final_state(agent)
        if expected:
            assert c_state == expected, f'c final state mismatch for {agent}'
        assert c_state == py_monitor.state

    if checked == 0:
        pytest.skip('no capture fixtures found')
