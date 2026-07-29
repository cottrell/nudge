#!/usr/bin/env python3
"""One multiplexing process per swarm; pane semantics live in PaneWorker."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "swarm"))
from common import babysit_runtime_paths, load_config  # noqa: E402
from pane_worker import PaneWorker, load_spec  # noqa: E402


def pane_spec(cfg, pane: str, cache: dict | None = None) -> dict | None:
    paths = babysit_runtime_paths(cfg, pane)
    path = Path(paths["spec"])
    cached = cache.get(pane) if cache is not None else None
    spec, current = load_spec(path, cached)
    if cache is not None:
        if current is None:
            cache.pop(pane, None)
        else:
            cache[pane] = current
    if spec is not None:
        spec = {**spec, "state_file": paths["state"]}
    return spec


def tasks_enabled(cfg) -> bool:
    return (cfg.runtime_dir / "tasks" / "enabled.json").exists()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: session_worker.py <swarm-yaml>", file=sys.stderr)
        return 2
    cfg_path = sys.argv[1]
    cfg = load_config(cfg_path)
    workers = {pane.pane: PaneWorker(cfg.session_name, pane.pane) for pane in cfg.panes}
    spec_cache = {}
    next_tasks = 0.0
    config_mtime = Path(cfg_path).stat().st_mtime
    print(f"session worker started: {cfg.session_name} panes={len(workers)}", flush=True)
    while True:
        try:
            mtime = Path(cfg_path).stat().st_mtime
            if mtime != config_mtime:
                cfg = load_config(cfg_path); config_mtime = mtime
                for pane in cfg.panes:
                    workers.setdefault(pane.pane, PaneWorker(cfg.session_name, pane.pane))
                for pane in list(workers):
                    if pane not in {p.pane for p in cfg.panes}:
                        workers.pop(pane)
                        spec_cache.pop(pane, None)
        except OSError:
            pass
        now = time.time()
        for pane, worker in workers.items():
            try:
                spec = pane_spec(cfg, pane, spec_cache)
                if spec: worker.tick(spec, now)
            except Exception as exc:
                print(f"pane {pane} error: {exc}", flush=True)
        if tasks_enabled(cfg) and now >= next_tasks:
            try:
                from tasksctl import dispatch_once, save_worker_state
                dispatch_once(cfg)
            except Exception as exc:
                print(f"tasks dispatch error: {exc}", flush=True)
            next_tasks = now + cfg.tasks.poll_secs
            try:
                save_worker_state(cfg, next_tasks)
            except Exception as exc:
                print(f"tasks heartbeat error: {exc}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
