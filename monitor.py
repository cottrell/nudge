#!/usr/bin/env python3
"""
Reference implementation and test oracle.

This file defines the expected behavior for agent state classification.
The C implementation (monitor.c) is the production backend and must match
this file's output. The test 'test_fixture_replay_c_matches_python_final_state'
verifies parity between C and Python.

When adding patterns:
1. Add to this file first (easier to test/read)
2. Mirror in monitor.c (PATS array)
3. Run 'make test' to verify parity

Usage:
    tmux pipe-pane -t mysession "python monitor.py --agent claude --socket /tmp/mysession.sock"
    echo "status" | nc -U /tmp/mysession.sock
"""
import sys
import re
import socket
import threading
import json
import os
import argparse
from datetime import datetime, timezone
from collections import deque
from time import monotonic

IDLE_HOLDOFF_SECS = 1.0
QUIET_IDLE_SECS = 2.0
_IDLE_HOLDOFF_AGENTS = {'gemini', 'copilot', 'codex', 'qwen', 'vibe'}

# Keyed by agent type, then state name -> list of patterns (case-insensitive)
# Patterns sourced directly from each CLI's own output / source.
# State precedence: first match wins, so put more specific states first.
# Initial state is always 'unknown' until a line matches.
PATTERNS = {
    'claude': {
        # idle checked first — these lines are definitive
        'idle':         [r'^\s*>\s*$', r'^❯'],
        # spinner verbs + braille dots cycling: ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏
        'working':      [r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]', r'[·✢✳∗✻✽]'],
        # 529 overloaded is distinct from 429 rate limit but both mean "back off"
        'rate_limited': [r'rate_limit_error', r'overloaded_error', r'Overloaded',
                         r'exceed.*rate limit', r'429', r'529',
                         r'Retrying in \d+ seconds'],
        'error':        [r'API Error:', r'authentication_error', r'invalid_request_error',
                         r'"type"\s*:\s*"error"'],
    },
    'gemini': {
        # same braille spinner, "Thinking ..." with timer
        'working':      [r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]', r'Thinking \.\.\.', r'esc to cancel'],
        'rate_limited': [r'Quota exceeded', r'quota', r'rate.?limit', r'429',
                         r'Too Many Requests'],
        'idle':         [r'^\s*[>!*]\s*$', r'Type your message', r'\? for shortcuts'],
        'error':        [r'✕\s+Error', r'✕\s+API Error', r'Request failed after all retries'],
    },
    'codex': {
        'working':      [r'working', r'esc to interrupt', r'thinking', r'writing', r'running'],
        'rate_limited': [r'rate.?limited', r'429'],
        'idle':         [r'^\s*\$\s*$', r'^\s*[›>]\s+', r'Reply with exactly', r'\? for shortcuts', r'context left'],
        'error':        [r'Error:'],
    },
    'copilot': {
        'working':      [r'thinking', r'writing', r'running', r'loading environment', r'esc to interrupt'],
        'rate_limited': [r'rate.?limit', r'429', r'too many requests'],
        'idle':         [r'^\s*[›>]\s*$', r'type @ to mention files', r'type your message'],
        'error':        [r'Error:'],
    },
    'vibe': {
        'working':      [r'esc to interrupt'],
        'rate_limited': [r'Rate limits exceeded'],
        'idle':         [r'^\s*>\s*$'],
        'error':        [r'Error:'],
    },
    'qwen': {
        # braille spinner from cli-spinners "dots" set
        'working':      [r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]'],
        'rate_limited': [r'rate.?limit', r'429', r'too many requests'],
        'idle':         [r'^\s*[>!*]\s*$', r'Type your message', r'\? for shortcuts'],
        'error':        [r'Error:', r'error'],
    },
}

VALID_AGENTS = ('claude', 'codex', 'copilot', 'gemini', 'vibe', 'qwen')
VALID_AGENTS_TEXT = ', '.join(VALID_AGENTS)

# Per-agent patterns to extract % of quota remaining from terminal output.
# Each entry is a list of (pattern, kind) pairs tried in order.
# kind='pct_left'      → group(1) is % remaining directly
# kind='pct_used'      → group(1) is % used; remaining = 100 - N
# kind='hours_used'    → group(1)=used, group(2)=total hours; remaining = (total-used)/total*100
_USAGE_PATTERNS: dict[str, list[tuple[re.Pattern, str]] | None] = {
    'claude': [
        # /usage output: "4.2 / 5.0 hours" (used/total)
        (re.compile(r'(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*hours', re.IGNORECASE), 'hours_used'),
        # /usage may also show "87% left" or "13% used"
        (re.compile(r'(\d+)%\s*left', re.IGNORECASE), 'pct_left'),
        (re.compile(r'(\d+)%\s*used', re.IGNORECASE), 'pct_used'),
    ],
    'codex': [
        (re.compile(r'(\d+)%\s*left', re.IGNORECASE), 'pct_left'),
    ],
    'gemini': [
        (re.compile(r'(\d+)%\s*left', re.IGNORECASE), 'pct_left'),
    ],
    'copilot': [
        (re.compile(r'(\d+)%\s*left', re.IGNORECASE), 'pct_left'),
    ],
    'qwen': [
        (re.compile(r'(\d+)%\s*left', re.IGNORECASE), 'pct_left'),
    ],
    'vibe': None,
}


_ANSI = re.compile(
    r'\x1b(?:'
    r'[@-Z\\-_]'           # Fe sequences (single char after ESC)
    r'|\[[0-?]*[ -/]*[@-~]'  # CSI sequences (ESC [ ... final)
    r'|\][^\x07]*\x07'      # OSC sequences (ESC ] ... BEL)
    r'|[0-9;]*[a-zA-Z]'     # catch-all for remaining sequences
    r')'
    r'|[\x00-\x08\x0b-\x1f\x7f]'  # other control chars except \t \n
)

def strip_ansi(s):
    return _ANSI.sub('', s)

_CLAUDE_WORKING_MARKERS = re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏·✢✳∗✻✽]|esc to cancel', re.IGNORECASE)

def _is_claude_idle(line):
    line = line.strip()
    if line == '>':
        return True
    if re.fullmatch(r'❯[\s\xa0]*', line):
        return True
    if '--INSERT--' in line or '-- INSERT --' in line:
        return True
    if not re.search(r'❯[\s\xa0]*$', line):
        return False
    return _CLAUDE_WORKING_MARKERS.search(line) is None

def _is_claude_insert_redraw(line):
    line = line.strip()
    return line.startswith('--INSERT--') or '-- INSERT --' in line


def _has_braille(line):
    return re.search(r'[\u2800-\u28ff]', line) is not None


def _is_vibe_logo_line(line):
    return ('Mistral Vibe' in line or
            ('models' in line and 'MCP server' in line) or
            'skills' in line)


def _is_vibe_idle(line):
    line = line.strip()
    return line == '>' or '│ >' in line


class Monitor:
    def __init__(self, agent_type='unknown', socket_path=None, log_size=500, debug_file=None, state_log=None):
        if agent_type not in VALID_AGENTS:
            raise ValueError(f"unknown agent type: {agent_type}")
        self.agent_type = agent_type
        self.socket_path = socket_path
        self.state = 'unknown'
        self.log = deque(maxlen=log_size)
        self.patterns = PATTERNS.get(agent_type, {})
        self._lock = threading.Lock()
        self._debug = open(debug_file, 'wb') if debug_file else None
        self._state_log = open(state_log, 'w', encoding='utf-8') if state_log else None
        # ring buffer of last 20 raw lines for debug query
        self._raw = deque(maxlen=20)
        self._usage_pct: int | None = None  # % of quota remaining (0-100), None if unseen
        self._last_working_at = None
        self._last_ingest_at = None
        self._pending_idle_at = None
        self._pending_idle_line = None
        self._emit_state('init', self.state)

    def _emit_state(self, event, state, line=None):
        if not self._state_log:
            return
        payload = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'event': event,
            'agent': self.agent_type,
            'state': state,
        }
        if line is not None:
            payload['line'] = line
        self._state_log.write(json.dumps(payload) + '\n')
        self._state_log.flush()

    def _refresh_state_locked(self, now=None):
        if now is None:
            now = monotonic()
        if self.agent_type not in _IDLE_HOLDOFF_AGENTS:
            return False
        if self.state != 'working':
            return False
        if self._pending_idle_at is None or self._last_working_at is None:
            if self._last_ingest_at is None or self._last_working_at is None:
                return False
            if now - self._last_working_at < IDLE_HOLDOFF_SECS:
                return False
            if now - self._last_ingest_at < QUIET_IDLE_SECS:
                return False
            self.state = 'idle'
            self._emit_state('change', self.state)
            return True
        if now - self._last_working_at < IDLE_HOLDOFF_SECS:
            return False
        self.state = 'idle'
        self._emit_state('change', self.state, self._pending_idle_line)
        self._pending_idle_at = None
        self._pending_idle_line = None
        return True

    def classify(self, line):
        has_sync = '\x1b[?2026' in line
        # Skip title bar updates (contain OSC sequences like ]0;)
        if '\x1b]' in line and 'Claude Code' in line:
            return None  # Don't classify title bar as working
        line = strip_ansi(line)
        if self.agent_type == 'claude' and _is_claude_idle(line):
            return 'idle'
        if self.agent_type == 'claude' and _is_claude_insert_redraw(line):
            return 'idle'
        if self.agent_type == 'vibe' and _is_vibe_idle(line):
            return 'idle'
        if self.agent_type in {'gemini', 'qwen'} and _has_braille(line):
            return 'working'
        if self.agent_type == 'vibe' and 'esc to interrupt' in line.lower():
            return 'working'
        if self.agent_type == 'vibe' and _has_braille(line) and not _is_vibe_logo_line(line) and 'analyse' in line.lower():
            return 'working'
        if self.agent_type == 'claude' and has_sync and line.strip():
            return 'working'
        for state, pats in self.patterns.items():
            for p in pats:
                if re.search(p, line, re.IGNORECASE):
                    return state
        return None

    def _extract_usage(self, line: str) -> None:
        patterns = _USAGE_PATTERNS.get(self.agent_type)
        if not patterns:
            return
        for pat, kind in patterns:
            m = pat.search(line)
            if not m:
                continue
            try:
                if kind == 'hours_used':
                    used, total = float(m.group(1)), float(m.group(2))
                    if total > 0:
                        self._usage_pct = round((1.0 - used / total) * 100)
                elif kind == 'pct_used':
                    self._usage_pct = max(0, 100 - int(m.group(1)))
                else:  # pct_left
                    self._usage_pct = int(m.group(1))
            except (ValueError, ZeroDivisionError):
                continue
            break

    def ingest(self, line):
        raw = line.rstrip('\n')
        if self._debug:
            self._debug.write(repr(raw).encode() + b'\n')
            self._debug.flush()
        line = raw.rstrip()
        with self._lock:
            self._last_ingest_at = monotonic()
            self._raw.append(raw)
            self.log.append(line)
            self._extract_usage(line)
            self._refresh_state_locked()
            new_state = self.classify(line)
            now = monotonic()
            if new_state == 'working':
                self._last_working_at = now
                self._pending_idle_at = None
                self._pending_idle_line = None
            elif self.agent_type in _IDLE_HOLDOFF_AGENTS and new_state == 'idle' and self._last_working_at is not None:
                if now - self._last_working_at < IDLE_HOLDOFF_SECS:
                    self._pending_idle_at = now
                    self._pending_idle_line = line
                    new_state = None
            if new_state and new_state != self.state:
                self.state = new_state
                self._emit_state('change', self.state, line)

    def query(self, cmd):
        cmd = cmd.strip()
        with self._lock:
            if cmd == 'status':
                result: dict = {'state': self.state}
                if self._usage_pct is not None:
                    result['usage_pct'] = self._usage_pct
                return result
            elif cmd == 'log':
                return {'log': list(self.log)[-50:]}
            elif cmd == 'raw':
                return {'raw': list(self._raw)}
            elif cmd == 'tail':
                return {'line': self.log[-1] if self.log else None}
            else:
                return {'error': f'unknown command: {cmd}'}

    def _handle_client(self, conn):
        try:
            data = conn.recv(256).decode().strip()
            resp = json.dumps(self.query(data)) + '\n'
            conn.sendall(resp.encode())
        finally:
            conn.close()

    def serve(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.socket_path)
        srv.listen(5)
        try:
            while True:
                conn, _ = srv.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
        finally:
            srv.close()

    def serve_http(self, port):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        monitor = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                cmd = self.path.lstrip('/')  # /status -> status, /log -> log
                result = monitor.query(cmd or 'status')
                body = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass  # silence request logs

        HTTPServer(('', port), Handler).serve_forever()

    def run(self, http_port=None):
        if self.socket_path:
            threading.Thread(target=self.serve, daemon=True).start()
        if http_port:
            threading.Thread(target=self.serve_http, args=(http_port,), daemon=True).start()
        threading.Thread(target=self._tick, daemon=True).start()
        for line in sys.stdin:
            self.ingest(line)

    def _tick(self):
        while True:
            with self._lock:
                self._refresh_state_locked()
            threading.Event().wait(0.1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog=f'Valid agent types: {VALID_AGENTS_TEXT}'
    )
    parser.add_argument('--agent', required=True, help=f'Agent type: {VALID_AGENTS_TEXT}')
    parser.add_argument('--socket', default=None, help='Unix socket path')
    parser.add_argument('--http-port', type=int, default=None, help='Optional HTTP port')
    parser.add_argument('--debug', default=None, metavar='FILE', help='Write raw incoming lines to FILE (use repr encoding)')
    parser.add_argument('--state-log', default=None, metavar='FILE', help='Append state init/change events to FILE as JSONL')
    args = parser.parse_args()

    try:
        m = Monitor(agent_type=args.agent, socket_path=args.socket, debug_file=args.debug, state_log=args.state_log)
    except ValueError as e:
        print(f"{e}. Valid agent types: {VALID_AGENTS_TEXT}", file=sys.stderr)
        sys.exit(2)
    m.run(http_port=args.http_port)
