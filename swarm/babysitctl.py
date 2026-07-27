#!/usr/bin/env python3
"""Control the one session worker; ``babysit`` is its optional prompt group."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

try:
    from .common import ROOT_DIR, SwarmConfig, babysit_runtime_paths, write_runtime_map
except ImportError:
    from common import ROOT_DIR, SwarmConfig, babysit_runtime_paths, write_runtime_map


def pid_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["pid"])


def log_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["log"])


def spec_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["spec"])


def state_path(cfg: SwarmConfig, pane: str) -> Path:
    return Path(babysit_runtime_paths(cfg, pane)["state"])


def supervisor_pid_path(cfg: SwarmConfig) -> Path:
    return cfg.runtime_dir / "session_worker.pid"


def supervisor_log_path(cfg: SwarmConfig) -> Path:
    return cfg.runtime_dir / "session_worker.log"


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def desired_spec(cfg: SwarmConfig, pane: str, interval: int, clear_every: int,
                 long_prompt: str, short_prompt: str, long_prompt_file: str = "",
                 short_prompt_file: str = "", via_log: bool = True) -> dict:
    pane_spec = next((p for p in cfg.panes if p.pane == pane), None)
    bs = pane_spec.babysit if pane_spec else None
    return {
        "session": cfg.session_name, "pane": pane,
        "target": f"{cfg.session_name}:{pane}", "interval_secs": interval,
        "clear_every": clear_every, "long_prompt": long_prompt,
        "short_prompt": short_prompt, "long_prompt_file": long_prompt_file,
        "short_prompt_file": short_prompt_file, "via_log": via_log,
        "quota_probe_secs": bs.quota_probe_secs if bs else 300,
        "ema_alpha": bs.ema_alpha if bs else .30,
        "ema_safety": bs.ema_safety if bs else .92,
        "ema_k_var": bs.ema_k_var if bs else 0.,
        "ema_warmup": bs.ema_warmup if bs else 3,
        "ema_min_wait": bs.ema_min_wait if bs else 30,
        "ema_max_wait": bs.ema_max_wait if bs else 1200,
        "agent": pane_spec.agent if pane_spec else "",
    }


def load_spec(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _wanted(cfg: SwarmConfig, include_babysit: bool, include_comms: bool) -> dict[str, dict]:
    out = {}
    for pane in cfg.panes:
        bs = pane.babysit
        if include_babysit and bs.enabled:
            out[pane.pane] = desired_spec(
                cfg, pane.pane, bs.interval_secs, bs.clear_every, bs.long_prompt,
                bs.short_prompt, bs.long_prompt_file.name if bs.long_prompt_file else "",
                bs.short_prompt_file.name if bs.short_prompt_file else "", bs.via_log,
            )
        elif include_comms and (pane.comms or bs.enabled):
            out[pane.pane] = desired_spec(cfg, pane.pane,
                bs.interval_secs if bs.enabled else 5, bs.clear_every if bs.enabled else 0,
                "", "", via_log=bs.via_log if bs.enabled else True)
    return out


def _start_supervisor(cfg: SwarmConfig, dry_run: bool) -> None:
    path = supervisor_pid_path(cfg)
    if path.exists():
        try:
            if process_running(int(path.read_text().strip())):
                return
        except ValueError:
            pass
    if dry_run:
        print(f"would start session worker for {cfg.session_name}")
        return
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    with supervisor_log_path(cfg).open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "session_worker.py"), str(cfg.path)],
            stdout=log, stderr=log, start_new_session=True, text=True,
        )
    path.write_text(f"{proc.pid}\n")


def _retire_legacy_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    """Retire only worker processes recorded for this session during migration."""
    for pane in cfg.panes:
        path = pid_path(cfg, pane.pane)
        if not path.exists():
            continue
        try:
            pid = int(path.read_text().strip())
            args = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="], capture_output=True,
                text=True, check=False,
            ).stdout
        except (OSError, ValueError):
            continue
        if not process_running(pid) or not ("babysit.py" in args or "pane_worker.py" in args):
            continue
        if dry_run:
            print(f"would retire legacy pane worker {cfg.session_name}:{pane.pane} pid={pid}")
        else:
            os.kill(pid, signal.SIGTERM)


def _apply(cfg: SwarmConfig, dry_run: bool, include_babysit: bool, include_comms: bool,
           label: str) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    wanted = _wanted(cfg, include_babysit, include_comms)
    for pane, spec in wanted.items():
        if not dry_run:
            spec_path(cfg, pane).write_text(json.dumps(spec, indent=2) + "\n")
    for pane_file in cfg.runtime_dir.glob("babysit-*.json"):
        pane = pane_file.name.removeprefix("babysit-").removesuffix(".json").replace("-", ".")
        if pane not in wanted and not dry_run:
            pane_file.unlink(missing_ok=True)
            state_path(cfg, pane).unlink(missing_ok=True)
            pid_path(cfg, pane).unlink(missing_ok=True)
    _retire_legacy_workers(cfg, dry_run)
    _start_supervisor(cfg, dry_run)
    if not dry_run and supervisor_pid_path(cfg).exists():
        # Keep legacy per-pane pid paths for status consumers. They all point at one PID.
        pid = supervisor_pid_path(cfg).read_text()
        for pane in wanted:
            pid_path(cfg, pane).write_text(pid)
    write_runtime_map(cfg)
    print(f"{'Planned' if dry_run else 'Started'} {label} for {cfg.session_name}")


def ensure_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    _apply(cfg, dry_run, False, True, "session worker")


def apply_babysit(cfg: SwarmConfig, dry_run: bool) -> None:
    _apply(cfg, dry_run, True, True, "session worker (with babysit prompts)")


def disable_babysit(cfg: SwarmConfig, dry_run: bool) -> None:
    _apply(cfg, dry_run, False, True, "session worker (babysit prompts disabled)")


def stop_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    path = supervisor_pid_path(cfg)
    pid = int(path.read_text().strip()) if path.exists() else 0
    if dry_run:
        print(f"would stop session worker for {cfg.session_name} pid={pid or '-'}")
        return
    if pid and process_running(pid):
        os.kill(pid, signal.SIGTERM)
    path.unlink(missing_ok=True)
    for pane in cfg.panes:
        pid_path(cfg, pane.pane).unlink(missing_ok=True)
        spec_path(cfg, pane.pane).unlink(missing_ok=True)
        state_path(cfg, pane.pane).unlink(missing_ok=True)
    write_runtime_map(cfg)
    print(f"Stopped session worker for {cfg.session_name}")


# Backwards-compatible API names; these never create per-pane Python processes.
def start(cfg: SwarmConfig, dry_run: bool) -> None: apply_babysit(cfg, dry_run)
def start_comms(cfg: SwarmConfig, dry_run: bool) -> None: ensure_workers(cfg, dry_run)
def stop(cfg: SwarmConfig, dry_run: bool) -> None: stop_workers(cfg, dry_run)


def status(cfg: SwarmConfig) -> None:
    try:
        from . import topology
    except ImportError:
        import topology
    topology.print_status(cfg)
