#!/usr/bin/env python3
"""
Process stdin line-by-line, classify state via regex patterns, expose state
over a Unix socket.

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
from collections import deque

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
        'working':      [r'thinking', r'writing', r'running'],
        'rate_limited': [r'rate.?limit', r'429'],
        'idle':         [r'^\$\s*$'],
        'error':        [r'Error:'],
    },
    'copilot': {
        'working':      [r'thinking', r'writing', r'running', r'loading environment', r'esc to interrupt'],
        'rate_limited': [r'rate.?limit', r'429', r'too many requests'],
        'idle':         [r'^\s*[›>]\s*$', r'type @ to mention files', r'type your message'],
        'error':        [r'Error:'],
    },
    'vibe': {
        # braille spinner + "(0s esc to interrupt)" hint
        'working':      [r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]', r'esc to interrupt'],
        'rate_limited': [r'Rate limits exceeded'],
        'idle':         [r'^\s*>\s*$'],
        'error':        [r'Error:'],
    },
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


class Monitor:
    def __init__(self, agent_type='unknown', socket_path=None, log_size=500, debug_file=None):
        self.agent_type = agent_type
        self.socket_path = socket_path
        self.state = 'unknown'
        self.log = deque(maxlen=log_size)
        self.patterns = PATTERNS.get(agent_type, {})
        self._lock = threading.Lock()
        self._debug = open(debug_file, 'wb') if debug_file else None
        # ring buffer of last 20 raw lines for debug query
        self._raw = deque(maxlen=20)

    def classify(self, line):
        # synchronized output marker — Claude uses this for in-place spinner updates
        if '\x1b[?2026' in line:
            return 'working'
        line = strip_ansi(line)
        for state, pats in self.patterns.items():
            for p in pats:
                if re.search(p, line, re.IGNORECASE):
                    return state
        return None

    def ingest(self, line):
        raw = line.rstrip('\n')
        if self._debug:
            self._debug.write(repr(raw).encode() + b'\n')
            self._debug.flush()
        line = raw.rstrip()
        with self._lock:
            self._raw.append(raw)
            self.log.append(line)
            new_state = self.classify(line)
            if new_state:
                self.state = new_state

    def query(self, cmd):
        cmd = cmd.strip()
        with self._lock:
            if cmd == 'status':
                return {'state': self.state}
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
        for line in sys.stdin:
            self.ingest(line)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', default='unknown', help='Agent type: claude, codex, copilot, gemini, vibe')
    parser.add_argument('--socket', default=None, help='Unix socket path')
    parser.add_argument('--http-port', type=int, default=None, help='Optional HTTP port')
    parser.add_argument('--debug', default=None, metavar='FILE', help='Write raw incoming lines to FILE (use repr encoding)')
    args = parser.parse_args()

    m = Monitor(agent_type=args.agent, socket_path=args.socket, debug_file=args.debug)
    m.run(http_port=args.http_port)
