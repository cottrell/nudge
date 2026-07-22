#!/usr/bin/env python3
"""Session-level tasks dispatcher loop.

Polls a task source (v1: backlog.md) and claims+delivers work to free panes
with nudge.tasks.enabled. Separate from babysit prompt nudges.

Usage: tasks_dispatch.py <swarm-yaml>
Env: AISWARM_TASKS_DRY_RUN=1 to never claim/send.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "swarm"))

from common import load_config  # noqa: E402
import tasksctl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: tasks_dispatch.py <swarm-yaml>", file=sys.stderr)
        return 2
    cfg_path = args[0]
    dry = os.environ.get("AISWARM_TASKS_DRY_RUN") == "1"
    while True:
        try:
            cfg = load_config(cfg_path)
            tasksctl.validate_tasks_config(cfg)
            poll = cfg.tasks.poll_secs
            actions = tasksctl.dispatch_once(cfg, dry_run=dry)
            if actions:
                print(
                    f"[{time.strftime('%H:%M:%S')}] dispatched {len(actions)} task(s)",
                    flush=True,
                )
            else:
                print(f"[{time.strftime('%H:%M:%S')}] idle (no free pane or candidates)", flush=True)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] error: {e}", flush=True)
            poll = 60
        time.sleep(max(5, int(poll)))


if __name__ == "__main__":
    raise SystemExit(main())
