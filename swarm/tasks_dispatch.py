#!/usr/bin/env python3
"""Session-level tasks dispatcher loop.

Polls a task source (v1: backlog) and claims+delivers work to free panes
with tasks enabled. Separate from babysit prompt nudges.

Usage: python swarm/tasks_dispatch.py <swarm-yaml>
   or: python -m swarm.tasks_dispatch <swarm-yaml>
Env: AISWARM_TASKS_DRY_RUN=1 to never claim/send.
"""
from __future__ import annotations

import os
import sys
import time

try:
    from .common import load_config
    from . import tasksctl
except ImportError:
    from common import load_config
    import tasksctl


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
                state = tasksctl.load_state(cfg)
                free = tasksctl.free_task_panes(cfg, state)
                assigned = list((state.get("assignments") or {}).keys())
                try:
                    n_cand = len(tasksctl.list_candidate_tasks(cfg))
                except Exception as e:
                    n_cand = f"error:{e}"
                print(
                    f"[{time.strftime('%H:%M:%S')}] idle free={free} "
                    f"assigned={assigned} candidates={n_cand}",
                    flush=True,
                )
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] error: {e}", flush=True)
            poll = 60
        time.sleep(max(5, int(poll)))


if __name__ == "__main__":
    raise SystemExit(main())
