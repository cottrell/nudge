#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time

from common import ROOT_DIR, SHELL_NAMES, SwarmConfig, load_config, write_runtime_map


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
    proc = subprocess.run(
        ["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"],
        text=True, capture_output=True
    )
    return '"state"' in proc.stdout


def monitor_state(cfg: SwarmConfig, pane: str) -> str:
    sock = socket_path(cfg, pane)
    proc = subprocess.run(
        ["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"],
        text=True, capture_output=True
    )
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
    else:
        write_runtime_map(cfg)
    print(f"{'Planned' if dry_run else 'Applied'} swarm topology for {cfg.session_name}:{cfg.window_name}")


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
        if brief:
            lines.append(f"{target} {pane.title} {monitor}")
        else:
            command = pane_current_command(cfg, pane.pane)
            lines.append(f"{target} title={pane.title} cmd={command or '-'} monitor={monitor} babysit={'on' if pane.babysit.enabled else 'off'}")
    return lines


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply tmux swarm topology from YAML config.")
    parser.add_argument("config", help="Path to YAML config")
    parser.add_argument("command", nargs="?", default="apply", choices=["apply", "status"])
    parser.add_argument("--attach", action="store_true", help="Attach to the tmux session after apply")
    parser.add_argument("--brief", action="store_true", help="With status, print a compact per-pane state view")
    parser.add_argument("--watch", action="store_true", help="With status, refresh the output in place until interrupted")
    parser.add_argument("--interval", type=float, default=1.0, help="Watch refresh interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print actions without changing tmux")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        if args.command == "apply":
            apply(cfg, args.dry_run)
        else:
            if args.interval <= 0:
                raise ValueError("--interval must be > 0")
            if args.watch:
                watch_status(cfg, args.brief, args.interval)
            else:
                print_status(cfg, args.brief)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.command == "apply" and args.attach and not args.dry_run:
        subprocess.run(["tmux", "attach", "-t", cfg.session_name], check=True, text=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
