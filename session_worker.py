#!/usr/bin/env python3
"""One multiplexed comms, babysit and tasks loop for a swarm session."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "swarm"))
from common import babysit_runtime_paths, load_config  # noqa: E402
from pane_worker import _deliver, _drain_comms, _log_nudge, _query_socket, _write_state  # noqa: E402


class PaneLoop:
    def __init__(self, cfg, pane: str):
        self.cfg, self.pane = cfg, pane
        self.last_poll = 0.0
        self.next_nudge = 0
        self.nonidle_since = 0
        self.nudge_count = 0

    def spec(self) -> dict | None:
        path = Path(babysit_runtime_paths(self.cfg, self.pane)["spec"])
        try:
            return json.loads(path.read_text()) if path.exists() else None
        except (OSError, json.JSONDecodeError):
            return None

    def tick(self, now: int) -> None:
        spec = self.spec()
        if not spec:
            return
        interval = int(spec.get("interval_secs") or 5)
        if time.time() - self.last_poll < min(5, interval):
            return
        self.last_poll = time.time()
        target = str(spec["target"])
        session = self.cfg.session_name
        state_file = babysit_runtime_paths(self.cfg, self.pane)["state"]
        state = _query_socket(f"/tmp/{session}_{self.pane}.sock").get("state", "")
        long_prompt = str(spec.get("long_prompt") or "")
        short_prompt = str(spec.get("short_prompt") or long_prompt)
        if state in ("idle", "rate_limited", ""):
            self.nonidle_since = 0
        elif not self.nonidle_since:
            self.nonidle_since = now
        if state == "idle":
            _drain_comms(session, target, self.pane)
            if long_prompt and not self.next_nudge:
                # Preserve the old startup behavior, but do it when the supervisor sees
                # a configured pane rather than at process creation.
                _log_nudge(session, target, "startup", long_prompt)
                _deliver(session, target, self.pane, long_prompt, "babysit_startup", spec.get("via_log", True))
                self.nudge_count += 1
                self.next_nudge = now + interval
            elif short_prompt and now >= self.next_nudge:
                if int(spec.get("clear_every") or 0) and self.nudge_count and self.nudge_count % int(spec["clear_every"]) == 0:
                    _deliver(session, target, self.pane, "/clear", "clear", spec.get("via_log", True))
                    _deliver(session, target, self.pane, long_prompt, "babysit_restore", spec.get("via_log", True))
                else:
                    _log_nudge(session, target, "idle", short_prompt)
                    _deliver(session, target, self.pane, short_prompt, "babysit", spec.get("via_log", True))
                self.nudge_count += 1
                self.next_nudge = now + interval
            action = "idle_nudge" if long_prompt else "comms_idle"
            _write_state(state_file, target, interval, state, action, now if long_prompt else 0,
                         0, now + min(5, interval), 0, self.next_nudge)
            return
        max_nonidle = int(spec.get("max_nonidle_secs") or 1800)
        force_at = self.nonidle_since + max_nonidle if long_prompt and self.nonidle_since and max_nonidle else 0
        if force_at and now >= force_at:
            _log_nudge(session, target, f"forced_{state or 'unknown'}", short_prompt)
            _deliver(session, target, self.pane, short_prompt, "babysit_forced", spec.get("via_log", True))
            self.nonidle_since = now
            self.next_nudge = now + interval
        _write_state(state_file, target, interval, state, f"wait_{state or 'unknown'}", 0,
                     self.nonidle_since, now + min(5, interval), force_at, self.next_nudge)


def tasks_enabled(cfg) -> bool:
    return (cfg.runtime_dir / "tasks" / "enabled.json").exists()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: session_worker.py <swarm-yaml>", file=sys.stderr)
        return 2
    cfg = load_config(sys.argv[1])
    loops = {pane.pane: PaneLoop(cfg, pane.pane) for pane in cfg.panes}
    next_tasks = 0.0
    print(f"session worker started: {cfg.session_name} panes={len(loops)}", flush=True)
    while True:
        now = int(time.time())
        for loop in loops.values():
            try:
                loop.tick(now)
            except Exception as exc:
                print(f"pane {loop.pane} error: {exc}", flush=True)
        if tasks_enabled(cfg) and time.time() >= next_tasks:
            try:
                from tasksctl import dispatch_once
                dispatch_once(cfg)
            except Exception as exc:
                print(f"tasks dispatch error: {exc}", flush=True)
            next_tasks = time.time() + cfg.tasks.poll_secs
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
