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
            pane.babysit.via_log,
        )
    return out


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


def start_worker(cfg: SwarmConfig, pane: str, interval: int, clear_every: int, long_prompt: str, short_prompt: str, long_prompt_file: str, short_prompt_file: str, via_log: bool, dry_run: bool) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"would start babysit for {cfg.session_name}:{pane} interval={interval} clear_every={clear_every}")
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
                print(f"would stop babysit for {cfg.session_name}:{pane} pid={pid}")
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
        if include_babysit and p.babysit.enabled:
            worker_desired[p.pane] = (
                p.babysit.interval_secs,
                p.babysit.clear_every,
                p.babysit.long_prompt,
                p.babysit.short_prompt,
                p.babysit.long_prompt_file.name if p.babysit.long_prompt_file else "",
                p.babysit.short_prompt_file.name if p.babysit.short_prompt_file else "",
                p.babysit.via_log,
            )
        elif include_comms and p.comms:
            worker_desired[p.pane] = (5, 0, "", "", "", "", True)

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
            stop_worker(cfg, pane, dry_run)
        start_worker(cfg, pane, interval, clear_every, long_prompt, short_prompt, lp_file, sp_file, via_log, dry_run)

    write_runtime_map(cfg)
    write_self_awareness_text(cfg)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
        print(f"wrote self-awareness note to {cfg.self_awareness_path}")
    print(f"{'Planned' if dry_run else 'Started'} {label} for {cfg.session_name}")


def start(cfg: SwarmConfig, dry_run: bool) -> None:
    _start_workers(cfg, dry_run, include_babysit=True, include_comms=True, label="workers (babysit+comms)")


def start_comms(cfg: SwarmConfig, dry_run: bool) -> None:
    _start_workers(cfg, dry_run, include_babysit=False, include_comms=True, label="workers (comms)")


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
            worker_panes[p.pane] = (5, 0, "", "", "", "", p.comms)  # via_log True for comms

    # Build rows for table output
    rows = []
    for pane in sorted(worker_panes):
        path = pid_path(cfg, pane)
        if not path.exists():
            rows.append((f"{cfg.session_name}:{pane}", "-", "-", "stopped", "-"))
            continue
        pid = int(path.read_text().strip())
        proc_state = "running" if process_running(pid) else "stale"
        note = ""
        spec = load_spec(spec_path(cfg, pane))
        if spec:
            tup = worker_panes[pane]
            if len(tup) == 7:
                di, dc, dlp, dsp, dlp_f, dsp_f, dvl = tup
            else:
                di, dc, dlp, dsp, dlp_f, dsp_f = tup
                dvl = True
            if spec != desired_spec(cfg, pane, di, dc, dlp, dsp, dlp_f, dsp_f, dvl):
                has_prompts = bool(spec.get("long_prompt") or spec.get("short_prompt"))
                pane_spec = next((p for p in cfg.panes if p.pane == pane), None)
                is_babysit_pane = bool(pane_spec and pane_spec.babysit.enabled)
                if is_babysit_pane and not has_prompts:
                    note = "comms only; babysit not started"
                else:
                    note = "drifted"
        next_str = "-"
        state_file = state_path(cfg, pane)
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                now = int(__import__("time").time())
                next_poll_at = int(data.get("next_poll_at") or 0)
                if next_poll_at > 0:
                    delta = max(0, next_poll_at - now)
                    next_str = "≤5s" if delta <= 0 else f"{delta}s"
            except Exception:
                next_str = "?"

        pane_obj = next((p for p in cfg.panes if p.pane == pane), None)
        mode = "babysit" if (pane_obj and pane_obj.babysit.enabled) else "comms"
        status_str = proc_state
        if note:
            status_str = f"{proc_state} ({note})"
        rows.append((f"{cfg.session_name}:{pane}", mode, str(pid), status_str, next_str))

    if not rows:
        print(f"{cfg.session_name}: no workers")
        return

    headers = ["Target", "Mode", "PID", "Status", "Next"]
    all_rows = [headers] + rows
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(headers))]
    print(f"{cfg.session_name} worker status")
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))
