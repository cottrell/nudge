#!/usr/bin/env python3
"""Compatibility entrypoint for one tasks dispatch pass.

Long-running dispatch belongs to ``session_worker.py``. Use ``aiswarm tasks
start`` to enable that group, or invoke this script for one direct pass.

Usage: python swarm/tasks_dispatch.py <swarm-yaml>
   or: python -m swarm.tasks_dispatch <swarm-yaml>
Env: AISWARM_TASKS_DRY_RUN=1 to never claim/send.
"""
from __future__ import annotations

import os
import sys

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
    cfg = load_config(cfg_path)
    tasksctl.validate_tasks_config(cfg)
    actions = tasksctl.dispatch_once(cfg, dry_run=os.environ.get("AISWARM_TASKS_DRY_RUN") == "1")
    print(f"dispatched {len(actions)} task(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
