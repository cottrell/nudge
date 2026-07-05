#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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
    # Proper check for a live process (our own workers).
    try:
        os.kill(pid, 0)  # signal 0 = no-op, just check existence/permission
        return True
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        # Fallback to /proc for unusual cases
        return Path(f"/proc/{pid}").exists()


def desired_spec(cfg: SwarmConfig, pane: str, interval: int, clear_every: int, long_prompt: str, short_prompt: str, long_prompt_file: str = "", short_prompt_file: str = "", via_log: bool = True) -> dict:
    pane_spec = next((p for p in cfg.panes if p.pane == pane), None)
    bs = pane_spec.babysit if pane_spec else None
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
        "via_log": via_log,
        "quota_probe_secs": bs.quota_probe_secs if bs else 300,
        "ema_alpha": bs.ema_alpha if bs else 0.30,
        "ema_safety": bs.ema_safety if bs else 0.92,
        "ema_k_var": bs.ema_k_var if bs else 0.0,
        "ema_warmup": bs.ema_warmup if bs else 3,
        "ema_min_wait": bs.ema_min_wait if bs else 30,
        "ema_max_wait": bs.ema_max_wait if bs else 1200,
    }


def load_spec(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _prompts_only_change(curr: dict | None, wanted: dict) -> bool:
    """True if curr and wanted differ only in the prompt strings (safe for hot update of babysit group)."""
    if not curr:
        return False
    keys = set(curr.keys()) | set(wanted.keys())
    for k in keys:
        if k in ("long_prompt", "short_prompt", "long_prompt_file", "short_prompt_file"):
            continue
        if curr.get(k) != wanted.get(k):
            return False
    return True


def start_worker(cfg: SwarmConfig, pane: str, interval: int, clear_every: int, long_prompt: str, short_prompt: str, long_prompt_file: str, short_prompt_file: str, via_log: bool, dry_run: bool) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"would start worker for {cfg.session_name}:{pane} interval={interval} clear_every={clear_every}")
        return
    pane_spec = next((p for p in cfg.panes if p.pane == pane), None)
    agent = pane_spec.agent if pane_spec else ""
    bs = pane_spec.babysit if pane_spec else None
    env = dict(
        **__import__("os").environ,
        BABYSIT_STATE_FILE=str(state_path(cfg, pane)),
        BABYSIT_AGENT=agent or "",
        BABYSIT_CLEAR_EVERY=str(clear_every),
        BABYSIT_LONG_PROMPT_FILE=long_prompt_file,
        BABYSIT_SHORT_PROMPT_FILE=short_prompt_file,
        BABYSIT_VIA_LOG="1" if via_log else "0",
        BABYSIT_STATS_EVERY=str(bs.quota_probe_secs if bs else 300),
        BABYSIT_EMA_ALPHA=str(bs.ema_alpha if bs else 0.30),
        BABYSIT_EMA_SAFETY=str(bs.ema_safety if bs else 0.92),
        BABYSIT_EMA_K_VAR=str(bs.ema_k_var if bs else 0.0),
        BABYSIT_EMA_WARMUP=str(bs.ema_warmup if bs else 3),
        BABYSIT_EMA_MIN_WAIT=str(bs.ema_min_wait if bs else 30),
        BABYSIT_EMA_MAX_WAIT=str(bs.ema_max_wait if bs else 1200),
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
    spec_path(cfg, pane).write_text(json.dumps(desired_spec(cfg, pane, interval, clear_every, long_prompt, short_prompt, long_prompt_file, short_prompt_file, via_log), indent=2) + "\n")


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
                print(f"would stop worker for {cfg.session_name}:{pane} pid={pid}")
            else:
                os_kill(pid, signal.SIGTERM)
    finally:
        if not dry_run:
            path.unlink(missing_ok=True)
            spec_path(cfg, pane).unlink(missing_ok=True)
            state_path(cfg, pane).unlink(missing_ok=True)


def _start_workers(cfg: SwarmConfig, dry_run: bool, include_babysit: bool, include_comms: bool, label: str) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)

    worker_desired = {}
    for p in cfg.panes:
        has_babysit_config = p.babysit.enabled
        want_babysit_active = include_babysit and has_babysit_config

        if want_babysit_active:
            worker_desired[p.pane] = (
                p.babysit.interval_secs,
                p.babysit.clear_every,
                p.babysit.long_prompt,
                p.babysit.short_prompt,
                p.babysit.long_prompt_file.name if p.babysit.long_prompt_file else "",
                p.babysit.short_prompt_file.name if p.babysit.short_prompt_file else "",
                p.babysit.via_log,
            )
        elif include_comms and (p.comms or has_babysit_config):
            # Comms mode (or "babysit disabled" for a babysit-configured pane).
            # Keep the original interval/clear if this pane has babysit config,
            # so that disabling babysit can be a pure hot-update of prompts only
            # (no worker restart, no gap in Comms HB).
            if has_babysit_config:
                iv = p.babysit.interval_secs
                cl = p.babysit.clear_every
                via = p.babysit.via_log
            else:
                iv = 5
                cl = 0
                via = True
            worker_desired[p.pane] = (iv, cl, "", "", "", "", via)

    existing = {p.name.removeprefix("babysit-").removesuffix(".pid").replace("-", "."): p for p in cfg.runtime_dir.glob("babysit-*.pid")}
    for pane in sorted(existing):
        if pane not in worker_desired:
            stop_worker(cfg, pane, dry_run)

    for pane, (interval, clear_every, long_prompt, short_prompt, lp_file, sp_file, via_log) in worker_desired.items():
        path = pid_path(cfg, pane)
        wanted = desired_spec(cfg, pane, interval, clear_every, long_prompt, short_prompt, lp_file, sp_file, via_log)
        current_spec = load_spec(spec_path(cfg, pane))
        if path.exists():
            pid = int(path.read_text().strip())
            if process_running(pid) and current_spec == wanted:
                continue
            if process_running(pid) and _prompts_only_change(current_spec, wanted):
                # Dynamic toggle of babysit group: just update the spec on disk.
                # The running worker will pick it up on next cycle via _current_prompts().
                #
                # Limitation: this only hot-swaps the prompt *text* (and file metadata).
                # If babysit start/stop also changed non-prompt settings (interval, clear_every, EMA params),
                # _prompts_only_change will be False and we fall through to a full restart (correct).
                if not dry_run:
                    spec_path(cfg, pane).write_text(json.dumps(wanted, indent=2) + "\n")
                continue
            stop_worker(cfg, pane, dry_run)
        start_worker(cfg, pane, interval, clear_every, long_prompt, short_prompt, lp_file, sp_file, via_log, dry_run)

    write_runtime_map(cfg)
    write_self_awareness_text(cfg)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
        print(f"wrote self-awareness note to {cfg.self_awareness_path}")
    print(f"{'Planned' if dry_run else 'Started'} {label} for {cfg.session_name}")

# Naming note: "babysit-*" file prefixes and some function names are legacy for
# compatibility. The worker is the single IO loop; "babysit" specifically refers
# to the optional prompt-nudge group on top of the comms base.


def ensure_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    """Ensure the base worker loop (comms/IO group) is running for panes that need it. The babysit prompt group is optional on top."""
    _start_workers(cfg, dry_run, include_babysit=False, include_comms=True, label="workers")


def apply_babysit(cfg: SwarmConfig, dry_run: bool) -> None:
    """Turn on the babysit prompt group for panes with babysit.enabled in config (keeps/starts the worker loop)."""
    _start_workers(cfg, dry_run, include_babysit=True, include_comms=True, label="workers (with babysit prompts)")


def disable_babysit(cfg: SwarmConfig, dry_run: bool) -> None:
    """Turn off the babysit prompt group (comms worker loop remains active for messaging)."""
    _start_workers(cfg, dry_run, include_babysit=False, include_comms=True, label="workers (babysit prompts disabled)")


def stop_workers(cfg: SwarmConfig, dry_run: bool) -> None:
    """Fully stop all worker loops for the session (both comms and babysit groups)."""
    for path in cfg.runtime_dir.glob("babysit-*.pid"):
        pane = path.name.removeprefix("babysit-").removesuffix(".pid").replace("-", ".")
        stop_worker(cfg, pane, dry_run)
    if not dry_run:
        write_runtime_map(cfg)
        write_self_awareness_text(cfg)
    print(f"{'Planned stop for' if dry_run else 'Stopped'} workers for {cfg.session_name}")


# Back-compat shims (prefer the new explicit names: ensure_workers, apply_babysit, disable_babysit, stop_workers).
# The legacy names are kept so existing calls and running swarms continue to work.
def start(cfg: SwarmConfig, dry_run: bool) -> None:
    apply_babysit(cfg, dry_run)


def start_comms(cfg: SwarmConfig, dry_run: bool) -> None:
    ensure_workers(cfg, dry_run)


def stop(cfg: SwarmConfig, dry_run: bool) -> None:
    stop_workers(cfg, dry_run)


def status(cfg: SwarmConfig) -> None:
    try:
        from . import topology as swarm_topology
    except ImportError:
        import topology as swarm_topology
    swarm_topology.print_status(cfg)
