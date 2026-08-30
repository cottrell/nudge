#!/usr/bin/env python3
"""Control the one session worker; ``babysit`` is its optional prompt group."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

try:
    from .common import (
        ROOT_DIR, SwarmConfig, babysit_runtime_paths, format_until, load_until,
        write_runtime_map, write_until,
    )
except ImportError:
    from common import (
        ROOT_DIR, SwarmConfig, babysit_runtime_paths, format_until, load_until,
        write_runtime_map, write_until,
    )


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


def until_path(cfg: SwarmConfig) -> Path:
    # Underscore so this is not matched by the babysit-*.json pane-spec glob.
    return cfg.runtime_dir / "babysit_until.json"


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_pid(path: Path) -> int:
    try:
        return int(path.read_text().strip() or "0")
    except (OSError, ValueError):
        return 0


def _process_argv(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError as e:
        raise RuntimeError(f"cannot inspect session worker pid {pid}: {e}") from e
    return [part.decode(errors="replace") for part in raw.split(b"\0") if part]


def _validate_supervisor_pid(cfg: SwarmConfig) -> int:
    path = supervisor_pid_path(cfg)
    if not path.exists():
        raise RuntimeError(f"session worker pid file is missing: {path}")
    pid = _read_pid(path)
    if pid <= 0:
        raise RuntimeError(f"session worker pid file is malformed: {path}")
    if not process_running(pid):
        raise RuntimeError(f"session worker pid is stale: {pid}")
    argv = _process_argv(pid)
    expected_worker = (ROOT_DIR / "session_worker.py").resolve()
    expected_config = cfg.path.resolve()
    expected = [expected_worker, expected_config]
    actual = [Path(arg).resolve() for arg in argv[1:]]
    if actual != expected:
        raise RuntimeError(
            f"pid {pid} is not the session worker for {cfg.session_name}: "
            f"argv={argv!r}"
        )
    return pid


def desired_spec(cfg: SwarmConfig, pane: str, interval: int, clear_every: int,
                 long_prompt: str, short_prompt: str, long_prompt_file: str = "",
                 short_prompt_file: str = "", via_log: bool = True, simulate: bool = False) -> dict:
    pane_spec = next((p for p in cfg.panes if p.pane == pane), None)
    bs = pane_spec.babysit if pane_spec else None
    return {
        "session": cfg.session_name, "pane": pane,
        "target": f"{cfg.session_name}:{pane}", "interval_secs": interval,
        "clear_every": clear_every, "long_prompt": long_prompt,
        "short_prompt": short_prompt, "long_prompt_file": long_prompt_file,
        "short_prompt_file": short_prompt_file, "via_log": via_log,
        "simulate": simulate,
        "quota_probe_secs": bs.quota_probe_secs if bs else 300,
        "ema_alpha": bs.ema_alpha if bs else .30,
        "ema_safety": bs.ema_safety if bs else .92,
        "ema_k_var": bs.ema_k_var if bs else 0.,
        "ema_warmup": bs.ema_warmup if bs else 3,
        "ema_min_wait": bs.ema_min_wait if bs else 30,
        "ema_max_wait": bs.ema_max_wait if bs else 1200,
        "agent": pane_spec.agent if pane_spec else "",
        "monitor": pane_spec.monitor if pane_spec else False,
    }


def load_spec(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _wanted(cfg: SwarmConfig, include_babysit: bool, include_comms: bool, no_action: bool = False) -> dict[str, dict]:
    out = {}
    for pane in cfg.panes:
        bs = pane.babysit
        if include_babysit and bs.enabled:
            out[pane.pane] = desired_spec(
                cfg, pane.pane, bs.interval_secs, bs.clear_every, bs.long_prompt,
                bs.short_prompt, bs.long_prompt_file.name if bs.long_prompt_file else "",
                bs.short_prompt_file.name if bs.short_prompt_file else "", bs.via_log,
                simulate=no_action,
            )
        elif include_comms and (pane.comms or bs.enabled):
            out[pane.pane] = desired_spec(cfg, pane.pane,
                bs.interval_secs if bs.enabled else 5, bs.clear_every if bs.enabled else 0,
                "", "", via_log=bs.via_log if bs.enabled else True, simulate=no_action)
    return out


def _start_supervisor(cfg: SwarmConfig, dry_run: bool) -> None:
    path = supervisor_pid_path(cfg)
    if path.exists():
        if process_running(_read_pid(path)):
            return
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
           label: str, no_action: bool = False, quiet: bool = False,
           until: float | None = None) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    wanted = _wanted(cfg, include_babysit, include_comms, no_action)
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
    extra = f" until {format_until(until)}" if include_babysit and until is not None else ""
    if not quiet:
        print(f"{'Planned' if dry_run else 'Started'} {label} for {cfg.session_name}{extra}")


def ensure_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    _apply(cfg, dry_run, False, True, "session worker")


def restart_worker(cfg: SwarmConfig, dry_run: bool = False) -> None:
    pid = _validate_supervisor_pid(cfg)
    if dry_run:
        print(f"would restart session worker for {cfg.session_name} pid={pid}")
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
    while process_running(pid) and time.monotonic() < deadline:
        time.sleep(.05)
    if process_running(pid):
        raise RuntimeError(f"session worker pid {pid} did not stop within 10 seconds")
    supervisor_pid_path(cfg).unlink(missing_ok=True)
    _start_supervisor(cfg, dry_run=False)
    new_pid = _read_pid(supervisor_pid_path(cfg))
    if new_pid <= 0 or not process_running(new_pid):
        raise RuntimeError(f"replacement session worker failed to start for {cfg.session_name}")
    for pane in cfg.panes:
        legacy = pid_path(cfg, pane.pane)
        if legacy.exists():
            legacy.write_text(f"{new_pid}\n")
    write_runtime_map(cfg)
    print(f"Restarted session worker for {cfg.session_name} pid={new_pid}")


def apply_babysit(cfg: SwarmConfig, dry_run: bool, no_action: bool = False,
                  until: float | None = None) -> None:
    label = "session worker (with babysit prompts, simulate mode)" if no_action else "session worker (with babysit prompts)"
    _apply(cfg, dry_run, True, True, label, no_action, until=until)
    if not dry_run:
        write_until(until_path(cfg), until)


def disable_babysit(cfg: SwarmConfig, dry_run: bool, quiet: bool = False) -> None:
    _apply(cfg, dry_run, False, True, "session worker (babysit prompts disabled)", quiet=quiet)
    if not dry_run:
        write_until(until_path(cfg), None)


def expire_if_due(cfg: SwarmConfig, now: float | None = None) -> bool:
    path = until_path(cfg)
    until = load_until(path)
    if until is None:
        return False
    if (time.time() if now is None else now) < until:
        return False
    disable_babysit(cfg, dry_run=False, quiet=True)
    print(f"babysit group expired for {cfg.session_name}", flush=True)
    return True


def stop_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    path = supervisor_pid_path(cfg)
    pid = _read_pid(path) if path.exists() else 0
    if dry_run:
        print(f"would stop session worker for {cfg.session_name} pid={pid or '-'}")
        return
    if pid and process_running(pid):
        os.kill(pid, signal.SIGTERM)
    path.unlink(missing_ok=True)
    write_until(until_path(cfg), None)
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
    until = load_until(until_path(cfg))
    if until is not None:
        print(f"babysit until {format_until(until)}")
    try:
        from . import topology
    except ImportError:
        import topology
    topology.print_status(cfg)
