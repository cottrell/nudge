#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
import signal
import subprocess

try:
    from .common import ROOT_DIR, SwarmConfig, babysit_runtime_paths, write_runtime_map, write_self_awareness_text
except ImportError:
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


def desired_panes(cfg: SwarmConfig) -> dict[str, tuple[int, int, str, str, str, str]]:
    out: dict[str, tuple[int, int, str, str, str, str]] = {}
    for pane in cfg.panes:
        if not pane.babysit.enabled:
            continue
        out[pane.pane] = (
            pane.babysit.interval_secs,
            pane.babysit.clear_every,
            pane.babysit.long_prompt,
            pane.babysit.short_prompt,
            pane.babysit.long_prompt_file.name if pane.babysit.long_prompt_file else "",
            pane.babysit.short_prompt_file.name if pane.babysit.short_prompt_file else "",
        )
    return out


def desired_spec(cfg: SwarmConfig, pane: str, interval: int, clear_every: int, long_prompt: str, short_prompt: str, long_prompt_file: str = "", short_prompt_file: str = "") -> dict:
    return {
        "session": cfg.session_name,
        "pane": pane,
        "target": f"{cfg.session_name}:{pane}",
        "interval_secs": interval,
        "clear_every": clear_every,
        "long_prompt": long_prompt,
        "short_prompt": short_prompt,
        "long_prompt_file": long_prompt_file,
        "short_prompt_file": short_prompt_file,
    }


def load_spec(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def start_worker(cfg: SwarmConfig, pane: str, interval: int, clear_every: int, long_prompt: str, short_prompt: str, long_prompt_file: str, short_prompt_file: str, dry_run: bool) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"would start babysit for {cfg.session_name}:{pane} interval={interval} clear_every={clear_every}")
        return
    agent = next((p.agent for p in cfg.panes if p.pane == pane), "")
    env = dict(
        **__import__("os").environ,
        BABYSIT_STATE_FILE=str(state_path(cfg, pane)),
        BABYSIT_AGENT=agent,
        BABYSIT_CLEAR_EVERY=str(clear_every),
        BABYSIT_LONG_PROMPT_FILE=long_prompt_file,
        BABYSIT_SHORT_PROMPT_FILE=short_prompt_file,
    )
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
    spec_path(cfg, pane).write_text(json.dumps(desired_spec(cfg, pane, interval, clear_every, long_prompt, short_prompt, long_prompt_file, short_prompt_file), indent=2) + "\n")


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
    # Start worker for babysit or comms (one process handling both when both enabled)
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)

    # Expand for comms-only panes (use default poll interval)
    worker_desired = {}
    for p in cfg.panes:
        if p.babysit.enabled:
            worker_desired[p.pane] = (
                p.babysit.interval_secs,
                p.babysit.clear_every,
                p.babysit.long_prompt,
                p.babysit.short_prompt,
                p.babysit.long_prompt_file.name if p.babysit.long_prompt_file else "",
                p.babysit.short_prompt_file.name if p.babysit.short_prompt_file else "",
            )
        elif p.comms:
            # comms consumer only: poll frequently enough for delivery
            worker_desired[p.pane] = (5, 0, "", "", "", "")

    existing = {p.name.removeprefix("babysit-").removesuffix(".pid").replace("-", "."): p for p in cfg.runtime_dir.glob("babysit-*.pid")}
    for pane in sorted(existing):
        if pane not in worker_desired:
            stop_worker(cfg, pane, dry_run)

    for pane, (interval, clear_every, long_prompt, short_prompt, lp_file, sp_file) in worker_desired.items():
        path = pid_path(cfg, pane)
        wanted = desired_spec(cfg, pane, interval, clear_every, long_prompt, short_prompt, lp_file, sp_file)
        current_spec = load_spec(spec_path(cfg, pane))
        if path.exists():
            pid = int(path.read_text().strip())
            if process_running(pid) and current_spec == wanted:
                continue
            stop_worker(cfg, pane, dry_run)
        start_worker(cfg, pane, interval, clear_every, long_prompt, short_prompt, lp_file, sp_file, dry_run)

    write_runtime_map(cfg)
    write_self_awareness_text(cfg)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
        print(f"wrote self-awareness note to {cfg.self_awareness_path}")
    print(f"{'Planned' if dry_run else 'Applied'} workers (babysit+comms) for {cfg.session_name}")


def stop(cfg: SwarmConfig, dry_run: bool) -> None:
    for path in cfg.runtime_dir.glob("babysit-*.pid"):
        pane = path.name.removeprefix("babysit-").removesuffix(".pid").replace("-", ".")
        stop_worker(cfg, pane, dry_run)
    if not dry_run:
        write_runtime_map(cfg)
        write_self_awareness_text(cfg)
    print(f"{'Planned stop for' if dry_run else 'Stopped'} babysit workers for {cfg.session_name}")


def status(cfg: SwarmConfig) -> None:
    # Report workers for both babysit and comms panes
    worker_panes = {}
    for p in cfg.panes:
        if p.babysit.enabled:
            worker_panes[p.pane] = (
                p.babysit.interval_secs,
                p.babysit.clear_every,
                p.babysit.long_prompt,
                p.babysit.short_prompt,
                p.babysit.long_prompt_file.name if p.babysit.long_prompt_file else "",
                p.babysit.short_prompt_file.name if p.babysit.short_prompt_file else "",
            )
        elif p.comms:
            worker_panes[p.pane] = (5, 0, "", "", "", "")
    for pane in sorted(worker_panes):
        path = pid_path(cfg, pane)
        if not path.exists():
            print(f"{cfg.session_name}:{pane} stopped")
            continue
        pid = int(path.read_text().strip())
        state = "running" if process_running(pid) else "stale"
        drift = ""
        spec = load_spec(spec_path(cfg, pane))
        if spec:
            di, dc, dlp, dsp, dlp_f, dsp_f = worker_panes[pane]
            if spec != desired_spec(cfg, pane, di, dc, dlp, dsp, dlp_f, dsp_f):
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
