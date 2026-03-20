#!/usr/bin/env python3
from __future__ import annotations

import shlex
import subprocess
import sys
import time
import json

from common import ROOT_DIR, SHELL_NAMES, SWARM_CLI, SwarmConfig, write_runtime_map, write_self_awareness_text
from babysitctl import state_path as babysit_state_path


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def pane_count(cfg: SwarmConfig) -> int:
    proc = run("tmux", "list-panes", "-t", f"{cfg.session_name}:{cfg.window_name}", check=False)
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def socket_path(cfg: SwarmConfig, pane: str) -> str:
    return f"/tmp/{cfg.session_name}_{pane}.sock"


def ensure_grid(cfg: SwarmConfig, dry_run: bool) -> None:
    created_session = False
    created_window = False
    if run("tmux", "has-session", "-t", cfg.session_name, check=False).returncode != 0:
        if dry_run:
            print(f"would create tmux session {cfg.session_name}:{cfg.window_name}")
            created_session = True
        else:
            run("tmux", "new-session", "-d", "-s", cfg.session_name, "-n", cfg.window_name, "bash")
            created_session = True
    elif run("tmux", "list-windows", "-t", cfg.session_name, check=False).stdout.find(cfg.window_name) == -1:
        if dry_run:
            print(f"would create window {cfg.session_name}:{cfg.window_name}")
            created_window = True
        else:
            run("tmux", "new-window", "-t", cfg.session_name, "-n", cfg.window_name, "bash")
            created_window = True

    count = 1 if dry_run and (created_session or created_window) else pane_count(cfg)
    if count == 0 and not dry_run:
        raise RuntimeError(f"could not inspect panes for {cfg.session_name}:{cfg.window_name}")
    if count == 0 and dry_run:
        count = 1
    if count > 0 and count != cfg.pane_count and not (created_session or created_window):
        raise RuntimeError(
            f"{cfg.session_name}:{cfg.window_name} has {count} panes, config expects {cfg.pane_count}. "
            "Recreate the window/session before applying."
        )

    current_count = count
    while current_count < cfg.pane_count:
        if dry_run:
            print(f"would split window {cfg.session_name}:{cfg.window_name} to add pane 0.{current_count}")
            current_count += 1
            continue
        run("tmux", "split-window", "-t", f"{cfg.session_name}:{cfg.window_name}.0", "bash")
        run("tmux", "select-layout", "-t", f"{cfg.session_name}:{cfg.window_name}", "tiled")
        current_count = pane_count(cfg)
    if dry_run:
        print(f"would apply tiled layout to {cfg.session_name}:{cfg.window_name}")
    elif count == current_count:
        run("tmux", "select-layout", "-t", f"{cfg.session_name}:{cfg.window_name}", "tiled")


def socket_ready(session_name: str, pane: str) -> bool:
    sock = f"/tmp/{session_name}_{pane}.sock"
    proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True)
    return '"state"' in proc.stdout


def monitor_state(cfg: SwarmConfig, pane: str) -> str:
    sock = socket_path(cfg, pane)
    proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True)
    if proc.returncode != 0 or '"state"' not in proc.stdout:
        return "unreachable"
    for token in ('"working"', '"idle"', '"unknown"', '"rate_limited"', '"error"'):
        if token in proc.stdout:
            return token.strip('"')
    return "unparseable"


def ensure_monitor(cfg: SwarmConfig, pane: str, agent: str, dry_run: bool) -> None:
    if socket_ready(cfg.session_name, pane):
        return
    if dry_run:
        print(f"would attach monitor for {cfg.session_name}:{pane} ({agent})")
        return
    subprocess.run([str(ROOT_DIR / "attach.sh"), f"{cfg.session_name}:{pane}", agent], check=True, text=True)


def pane_current_command(cfg: SwarmConfig, pane: str) -> str:
    proc = run("tmux", "display-message", "-p", "-t", f"{cfg.session_name}:{pane}", "#{pane_current_command}")
    return proc.stdout.strip()


def ensure_title(cfg: SwarmConfig, pane: str, title: str, dry_run: bool) -> None:
    if dry_run:
        print(f"would set pane title for {cfg.session_name}:{pane}: {title}")
        return
    run("tmux", "select-pane", "-t", f"{cfg.session_name}:{pane}", "-T", title)


def shell_prefixed_command(title: str, command: str) -> str:
    prefix = shlex.quote(f"[{title}] ")
    return f"export PS1={prefix}\"$PS1\"; {command}"


def ensure_command(cfg: SwarmConfig, pane: str, title: str, command: str, dry_run: bool) -> None:
    command = shell_prefixed_command(title, command)
    if dry_run:
        print(f"would start command in {cfg.session_name}:{pane}: {command}")
        return
    current = pane_current_command(cfg, pane)
    if current and current not in SHELL_NAMES:
        return
    subprocess.run(["tmux", "send-keys", "-t", f"{cfg.session_name}:{pane}", "-l", "--", command], check=True, text=True)
    time.sleep(0.1)
    subprocess.run(["tmux", "send-keys", "-t", f"{cfg.session_name}:{pane}", "C-m"], check=True, text=True)


def broadcast(cfg: SwarmConfig, message: str, include_nonmonitored: bool, dry_run: bool) -> None:
    if not message.strip():
        raise ValueError("broadcast message must not be empty")
    sent = 0
    for pane in cfg.panes:
        if not include_nonmonitored and not pane.monitor:
            continue
        target = f"{cfg.session_name}:{pane.pane}"
        if dry_run:
            print(f"would broadcast to {target} ({pane.title})")
            sent += 1
            continue
        subprocess.run([str(ROOT_DIR / "tmux-send"), target, message], check=True, text=True)
        print(f"broadcast to {target} ({pane.title})")
        sent += 1
    if sent == 0:
        scope = "all panes" if include_nonmonitored else "monitored panes"
        raise ValueError(f"no {scope} matched for broadcast")


def apply(cfg: SwarmConfig, dry_run: bool) -> None:
    ensure_grid(cfg, dry_run)
    for pane in cfg.panes:
        if pane.monitor:
            ensure_monitor(cfg, pane.pane, pane.agent, dry_run)
    if not dry_run:
        time.sleep(0.2)
    for pane in cfg.panes:
        ensure_title(cfg, pane.pane, pane.title, dry_run)
        ensure_command(cfg, pane.pane, pane.title, pane.command, dry_run)
    if dry_run:
        print(f"would write runtime map to {cfg.runtime_map_path}")
        print(f"would write self-awareness note to {cfg.self_awareness_path}")
    else:
        write_runtime_map(cfg)
        write_self_awareness_text(cfg)
    print(f"{'Planned' if dry_run else 'Applied'} swarm topology for {cfg.session_name}:{cfg.window_name}")
    print()
    print("For AGENTS.md:")
    print()
    print("  - When using the swarm workflow, consult these files:")
    print(f"    - Runtime map: {cfg.runtime_map_path}")
    print(f"    - Self-awareness note: {cfg.self_awareness_path}")
    print()
    print("Operator reminders:")
    print()
    print(f"  - Status: python {SWARM_CLI} status {cfg.path} --brief")
    print(f"  - Watch: python {SWARM_CLI} status {cfg.path} --brief -w")
    print()


def status_lines(cfg: SwarmConfig, brief: bool = False) -> list[str]:
    lines: list[str] = []
    session_exists = run("tmux", "has-session", "-t", cfg.session_name, check=False).returncode == 0
    window_exists = run("tmux", "list-windows", "-t", cfg.session_name, check=False).stdout.find(cfg.window_name) != -1 if session_exists else False
    actual_count = pane_count(cfg) if window_exists else 0
    if brief:
        lines.append(f"{cfg.session_name}:{cfg.window_name} panes={actual_count}/{cfg.pane_count}" if window_exists else f"{cfg.session_name}:{cfg.window_name} missing")
    else:
        lines.append(f"session={cfg.session_name} window={cfg.window_name} exists={'yes' if window_exists else 'no'} panes={actual_count}/{cfg.pane_count}")
    if not window_exists:
        return lines
    for pane in cfg.panes:
        target = f"{cfg.session_name}:{pane.pane}"
        proc = run("tmux", "list-panes", "-t", target, check=False)
        if proc.returncode != 0:
            lines.append(f"{target} missing")
            continue
        monitor = monitor_state(cfg, pane.pane) if pane.monitor else "off"
        babysit_note = ""
        if pane.babysit.enabled:
            babysit_note = _format_babysit_note(cfg, pane.pane)
        if brief:
            lines.append(f"{target} {pane.title} {monitor}{babysit_note}")
        else:
            command = pane_current_command(cfg, pane.pane)
            lines.append(f"{target} title={pane.title} cmd={command or '-'} monitor={monitor} babysit={'on' if pane.babysit.enabled else 'off'}{babysit_note}")
    return lines


def _format_babysit_note(cfg: SwarmConfig, pane: str) -> str:
    path = babysit_state_path(cfg, pane)
    if not path.exists():
        return " babysit=?"
    try:
        data = json.loads(path.read_text())
    except Exception:
        return " babysit=?"
    now = int(time.time())
    next_poll_at = int(data.get("next_poll_at") or 0)
    last_monitor_state = str(data.get("last_monitor_state") or "").strip()
    next_force_at = int(data.get("next_force_nudge_at") or 0)
    parts: list[str] = []
    if next_poll_at > 0:
        parts.append(f"next={max(0, next_poll_at - now)}s")
    if next_force_at > 0 and last_monitor_state in {"unknown", "working", "error"}:
        parts.append(f"force={max(0, next_force_at - now)}s")
    return f" babysit[{', '.join(parts) if parts else '?'}]"


def print_status(cfg: SwarmConfig, brief: bool = False, in_place: bool = False) -> None:
    lines = status_lines(cfg, brief)
    text = "\n".join(lines)
    if in_place:
        sys.stdout.write("\x1b[H\x1b[2J")
        sys.stdout.write(text)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return
    print(text)


def watch_status(cfg: SwarmConfig, brief: bool, interval: float) -> None:
    try:
        while True:
            lines = status_lines(cfg, brief)
            lines.insert(0, f"watch interval={interval:.1f}s updated={time.strftime('%H:%M:%S')}")
            sys.stdout.write("\x1b[H\x1b[2J")
            sys.stdout.write("\n".join(lines))
            sys.stdout.write("\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        return
