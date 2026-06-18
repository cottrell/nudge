#!/usr/bin/env python3
"""Reference implementation for activity-based pane monitoring."""
import sys
import math
import socket
import threading
import json
import os
import argparse
from datetime import datetime, timezone
from collections import deque
from time import monotonic

DEFAULT_IDLE_SECS = 10.0

VALID_AGENTS = ('claude', 'codex', 'copilot', 'gemini', 'grok', 'vibe', 'qwen', 'antigravity')
VALID_AGENTS_TEXT = ', '.join(VALID_AGENTS)


class Monitor:
    def __init__(
        self,
        agent_type='unknown',
        socket_path=None,
        log_size=500,
        debug_file=None,
        state_log=None,
        idle_secs=DEFAULT_IDLE_SECS,
    ):
        if agent_type not in VALID_AGENTS:
            raise ValueError(f"unknown agent type: {agent_type}")
        if not math.isfinite(idle_secs) or idle_secs <= 0:
            raise ValueError("idle_secs must be positive")
        self.agent_type = agent_type
        self.socket_path = socket_path
        self.idle_secs = idle_secs
        self.state = 'unknown'
        self.log = deque(maxlen=log_size)
        self._lock = threading.Lock()
        self._debug = open(debug_file, 'wb') if debug_file else None
        self._state_log = open(state_log, 'w', encoding='utf-8') if state_log else None
        self._raw = deque(maxlen=20)
        self._last_ingest_at = None
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
        if self.state != 'working' or self._last_ingest_at is None:
            return False
        if now - self._last_ingest_at < self.idle_secs:
            return False
        self.state = 'idle'
        self._emit_state('change', self.state)
        return True

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
            if self.state != 'working':
                self.state = 'working'
                self._emit_state('change', self.state, line)

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

    def _cleanup(self):
        if self.socket_path and os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        if self._state_log:
            self._state_log.close()
        if self._debug:
            self._debug.close()

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

        class IPv6HTTPServer(HTTPServer):
            address_family = socket.AF_INET6

        IPv6HTTPServer(('::', port), Handler).serve_forever()

    def run(self, http_port=None):
        try:
            if self.socket_path:
                threading.Thread(target=self.serve, daemon=True).start()
            if http_port:
                threading.Thread(target=self.serve_http, args=(http_port,), daemon=True).start()
            threading.Thread(target=self._tick, daemon=True).start()
            for line in sys.stdin:
                self.ingest(line)
        finally:
            self._cleanup()

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
    parser.add_argument('--idle-secs', type=float, default=DEFAULT_IDLE_SECS, help='Seconds without pane output before reporting idle')
    parser.add_argument('--debug', default=None, metavar='FILE', help='Write raw incoming lines to FILE (use repr encoding)')
    parser.add_argument('--state-log', default=None, metavar='FILE', help='Append state init/change events to FILE as JSONL')
    args = parser.parse_args()

    try:
        m = Monitor(
            agent_type=args.agent,
            socket_path=args.socket,
            debug_file=args.debug,
            state_log=args.state_log,
            idle_secs=args.idle_secs,
        )
    except ValueError as e:
        print(f"{e}. Valid agent types: {VALID_AGENTS_TEXT}", file=sys.stderr)
        sys.exit(2)
    m.run(http_port=args.http_port)
