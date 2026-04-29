#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
import signal
import subprocess

from common import ROOT_DIR, SwarmConfig, babysit_runtime_paths, write_runtime_map, write_self_awareness_text


def pid_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["pid"])


def log_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["log"])


def spec_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["spec"])


def state_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["state"])


def process_running(pid: int) -> bool:
    try:
        Path(f"/proc/{pid}")
    except Exception:
        return False
    return Path(f"/proc/{pid}").exists()


def desired_panes(cfg: SwarmConfig) -> dict[str, tuple[int, int, str, str]]:
    out: dict[str, tuple[int, int, str, str]] = {}
    for pane in cfg.panes:
        if not pane.babysit.enabled:
            continue
        out[pane.pane] = (pane.babysit.interval_secs, pane.babysit.clear_every, pane.babysit.long_prompt, pane.babysit.short_prompt)
    return out


def desired_spec(cfg: SwarmConfig, pane: str, interval: int, clear_every: int, long_prompt: str, short_prompt: str) -> dict:
    return {
        "session": cfg.session_name,
        "pane": pane,
        "target": f"{cfg.session_name}:{pane}",
        "interval_secs": interval,
        "clear_every": clear_every,
        "long_prompt": long_prompt,
        "short_prompt": short_prompt,
    }


def load_spec(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def start_worker(cfg: SwarmConfig, pane: str, interval: int, long_prompt: str, short_prompt: str, dry_run: bool) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"would start babysit for {cfg.session_name}:{pane} interval={interval}")
        return
    agent = next((p.agent for p in cfg.panes if p.pane == pane), "")
    env = dict(**__import__("os").environ, BABYSIT_STATE_FILE=str(state_path(cfg, pane)), BABYSIT_AGENT=agent)
    with log_path(cfg, pane).open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "babysit.py"), f"{cfg.session_name}:{pane}", str(interval), long_prompt, short_prompt],
            stdout=log,
            stderr=log,
            start_new_session=True,
            text=True,
            env=env,
        )
    pid_path(cfg, pane).write_text(str(proc.pid))
    spec_path(cfg, pane).write_text(json.dumps(desired_spec(cfg, pane, interval, long_prompt, short_prompt), indent=2) + "\n")


def os_kill(pid: int, sig: signal.Signals) -> None:
    import os
    os.kill(pid, sig)


def stop_worker(cfg: SwarmConfig, pane: str, dry_run: bool) -> None:
    path = pid_path(cfg, pane)
    if not path.exists():
        return
    pid = int(path.read_text().strip())
    try:
        if process_running(pid):
            if dry_run:
                print(f"would stop babysit for {cfg.session_name}:{pane} pid={pid}")
            else:
                os_kill(pid, signal.SIGTERM)
    finally:
        if not dry_run:
            path.unlink(missing_ok=True)
            spec_path(cfg, pane).unlink(missing_ok=True)
            state_path(cfg, pane).unlink(missing_ok=True)


def apply(cfg: SwarmConfig, dry_run: bool) -> None:
    desired = desired_panes(cfg)
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)

    existing = {p.name.removeprefix("babysit-").removesuffix(".pid").replace("-", "."): p for p in cfg.runtime_dir.glob("babysit-*.pid")}
    for pane in sorted(existing):
        if pane not in desired:
            stop_worker(cfg, pane, dry_run)

    for pane, (interval, clear_every, long_prompt, short_prompt) in desired.items():
        path = pid_path(cfg, pane)
        wanted = desired_spec(cfg, pane, interval, clear_every, long_prompt, short_prompt)
        current_spec = load_spec(spec_path(cfg, pane))
        if path.exists():
            pid = int(path.read_text().strip())
            if process_running(pid) and current_spec == wanted:
                continue
            stop_worker(cfg, pane, dry_run)
        start_worker(cfg, pane, interval, clear_every, long_prompt, short_prompt, dry_run)

    write_runtime_map(cfg)
    write_self_awareness_text(cfg)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
        print(f"wrote self-awareness note to {cfg.self_awareness_path}")
    print(f"{'Planned' if dry_run else 'Applied'} babysit workers for {cfg.session_name}")


def stop(cfg: SwarmConfig, dry_run: bool) -> None:
    for path in cfg.runtime_dir.glob("babysit-*.pid"):
        pane = path.name.removeprefix("babysit-").removesuffix(".pid").replace("-", ".")
        stop_worker(cfg, pane, dry_run)
    if not dry_run:
        write_runtime_map(cfg)
        write_self_awareness_text(cfg)
    print(f"{'Planned stop for' if dry_run else 'Stopped'} babysit workers for {cfg.session_name}")


def status(cfg: SwarmConfig) -> None:
    desired = desired_panes(cfg)
    for pane in sorted(desired):
        path = pid_path(cfg, pane)
        if not path.exists():
            print(f"{cfg.session_name}:{pane} stopped")
            continue
        pid = int(path.read_text().strip())
        state = "running" if process_running(pid) else "stale"
        drift = ""
        spec = load_spec(spec_path(cfg, pane))
        if spec:
            desired_interval, desired_clear_every, desired_long_prompt, desired_short_prompt = desired[pane]
            if spec != desired_spec(cfg, pane, desired_interval, desired_clear_every, desired_long_prompt, desired_short_prompt):
                drift = " drifted"
        extra = ""
        state_file = state_path(cfg, pane)
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                now = int(__import__("time").time())
                next_poll_at = int(data.get("next_poll_at") or 0)
                if next_poll_at > 0:
                    extra = f" next={max(0, next_poll_at - now)}s"
            except Exception:
                extra = " next=?"
        print(f"{cfg.session_name}:{pane} {state}{drift} pid={pid}{extra}")
