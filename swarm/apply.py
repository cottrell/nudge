#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import time

from common import ROOT_DIR, SHELL_NAMES, SwarmConfig, load_config


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def pane_count(cfg: SwarmConfig) -> int:
    proc = run("tmux", "list-panes", "-t", f"{cfg.session_name}:{cfg.window_name}", check=False)
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def ensure_grid(cfg: SwarmConfig, dry_run: bool) -> None:
    created_session = False
    created_window = False
    if run("tmux", "has-session", "-t", cfg.session_name, check=False).returncode != 0:
        if dry_run:
            print(f"would create tmux session {cfg.session_name}:{cfg.window_name}")
            created_session = True
        else:
            run("tmux", "new-session", "-d", "-s", cfg.session_name, "-n", cfg.window_name, "bash")
    elif run("tmux", "list-windows", "-t", cfg.session_name, check=False).stdout.find(cfg.window_name) == -1:
        if dry_run:
            print(f"would create window {cfg.session_name}:{cfg.window_name}")
            created_window = True
        else:
            run("tmux", "new-window", "-t", cfg.session_name, "-n", cfg.window_name, "bash")

    count = 1 if dry_run and (created_session or created_window) else pane_count(cfg)
    if count == 0 and not dry_run:
        raise RuntimeError(f"could not inspect panes for {cfg.session_name}:{cfg.window_name}")
    if count == 0 and dry_run:
        count = 1
    if count > 0 and count != cfg.pane_count and not (dry_run and (created_session or created_window)):
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
        run("tmux", "split-window", "-t", f"{cfg.session_name}:{cfg.window_name}", "bash")
        current_count = pane_count(cfg)
    if dry_run:
        print(f"would apply tiled layout to {cfg.session_name}:{cfg.window_name}")
    else:
        run("tmux", "select-layout", "-t", f"{cfg.session_name}:{cfg.window_name}", "tiled")


def socket_ready(session_name: str, pane: str) -> bool:
    sock = f"/tmp/{session_name}_{pane}.sock"
    proc = subprocess.run(
        ["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"],
        text=True, capture_output=True
    )
    return '"state"' in proc.stdout


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


def ensure_command(cfg: SwarmConfig, pane: str, command: str, dry_run: bool) -> None:
    if dry_run:
        print(f"would start command in {cfg.session_name}:{pane}: {command}")
        return
    current = pane_current_command(cfg, pane)
    if current and current not in SHELL_NAMES:
        return
    subprocess.run(["tmux", "send-keys", "-t", f"{cfg.session_name}:{pane}", "-l", "--", command], check=True, text=True)
    time.sleep(0.1)
    subprocess.run(["tmux", "send-keys", "-t", f"{cfg.session_name}:{pane}", "C-m"], check=True, text=True)


def apply(cfg: SwarmConfig, dry_run: bool) -> None:
    ensure_grid(cfg, dry_run)
    for pane in cfg.panes:
        if pane.monitor:
            ensure_monitor(cfg, pane.pane, pane.agent, dry_run)
    if not dry_run:
        time.sleep(0.2)
    for pane in cfg.panes:
        ensure_command(cfg, pane.pane, pane.command, dry_run)
    print(f"{'Planned' if dry_run else 'Applied'} swarm topology for {cfg.session_name}:{cfg.window_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply tmux swarm topology from YAML config.")
    parser.add_argument("config", help="Path to YAML config")
    parser.add_argument("--attach", action="store_true", help="Attach to the tmux session after apply")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print actions without changing tmux")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        apply(cfg, args.dry_run)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.attach and not args.dry_run:
        subprocess.run(["tmux", "attach", "-t", cfg.session_name], check=True, text=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
