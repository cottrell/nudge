#!/usr/bin/env python3
from __future__ import annotations

import re
import shlex
from datetime import datetime
import subprocess
import sys
import time
import json

from common import (
    AGENT_STATS_CMD,
    ROOT_DIR,
    SHELL_NAMES,
    SWARM_CLI,
    SwarmConfig,
    WindowSpec,
    write_runtime_map,
    write_self_awareness_text,
)

from babysitctl import pid_path as babysit_pid_path, state_path as babysit_state_path


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def _window_pane_count(session_name: str, window_name: str) -> int:
    proc = run("tmux", "list-panes", "-t", f"{session_name}:{window_name}", check=False)
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def socket_path(cfg: SwarmConfig, pane: str) -> str:
    return f"/tmp/{cfg.session_name}_{pane}.sock"


def _ensure_window(
    session_name: str,
    win: WindowSpec,
    dry_run: bool,
    is_first: bool = False,
    allow_expand_existing: bool = False,
) -> None:
    target = f"{session_name}:{win.window_name}"
    expected = len(win.panes)
    existing_windows = run("tmux", "list-windows", "-t", session_name, "-F", "#{window_name}", check=False).stdout
    win_exists = win.window_name in existing_windows.splitlines()

    if not win_exists:
        if dry_run:
            print(f"would create window {target}")
        else:
            if is_first:
                # first window was already created with the session
                run("tmux", "rename-window", "-t", f"{session_name}:0", win.window_name)
            else:
                run("tmux", "new-window", "-t", session_name, "-n", win.window_name, "bash")
        count = 1
    else:
        count = _window_pane_count(session_name, win.window_name)
        if count == 0 and not dry_run:
            raise RuntimeError(f"could not inspect panes for {target}")
        if count != expected and not allow_expand_existing:
            raise RuntimeError(
                f"{target} has {count} panes, config expects {expected}. "
                "Recreate the window/session before applying."
            )

    while count < expected:
        if dry_run:
            print(f"would split {target} to add pane {win.window_name}.{count}")
            count += 1
            continue
        run("tmux", "split-window", "-t", f"{target}.0", "bash")
        run("tmux", "select-layout", "-t", target, win.layout)
        count = _window_pane_count(session_name, win.window_name)

    if dry_run:
        print(f"would apply layout {win.layout!r} to {target}")
    else:
        run("tmux", "select-layout", "-t", target, win.layout)


def setup_grid(cfg: SwarmConfig, dry_run: bool) -> None:
    """Create the tmux session and all windows. Idempotent. Can be replaced by tmuxp load."""
    session_exists = run("tmux", "has-session", "-t", f"={cfg.session_name}", check=False).returncode == 0
    created_session = False
    if not session_exists:
        if dry_run:
            print(f"would create session {cfg.session_name}")
        else:
            run("tmux", "new-session", "-d", "-s", cfg.session_name, "-n", cfg.windows[0].window_name, "bash")
        created_session = True
    for i, win in enumerate(cfg.windows):
        _ensure_window(
            cfg.session_name,
            win,
            dry_run,
            is_first=(i == 0 and not session_exists),
            allow_expand_existing=(i == 0 and created_session),
        )


def socket_ready(session_name: str, pane: str) -> bool:
    sock = f"/tmp/{session_name}_{pane}.sock"
    proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True)
    return '"state"' in proc.stdout




def _query_monitor(cfg: SwarmConfig, pane: str) -> dict:
    sock = socket_path(cfg, pane)
    proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True)
    if proc.returncode != 0 or '"state"' not in proc.stdout:
        return {'state': 'unreachable'}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {'state': 'unparseable'}


def monitor_state(cfg: SwarmConfig, pane: str) -> str:
    return _query_monitor(cfg, pane).get('state', 'unreachable')


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
    subprocess.run([str(ROOT_DIR / "tmux-send"), "--no-prefix", f"{cfg.session_name}:{pane}", command], check=True, text=True)



def capture_and_classify(cfg: SwarmConfig, pane: str) -> None:
    target = f"{cfg.session_name}:{pane}"
    proc = subprocess.run(["tmux", "capture-pane", "-t", target, "-p"], text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"could not capture {target}")
        return
    
    # Try to find agent type from config
    agent_type = "unknown"
    for p in cfg.panes:
        if p.pane == pane:
            agent_type = p.agent
            break
    
    print(f"--- Capture {target} (agent={agent_type}) ---")
    print(proc.stdout)
    print("--- Analysis ---")
    
    sys.path.append(str(ROOT_DIR))
    import monitor
    try:
        m = monitor.Monitor(agent_type=agent_type)
        for line in proc.stdout.splitlines():
            m.ingest(line + "\n")
        status = m.query("status")
        print(json.dumps(status, indent=2))
    except Exception as e:
        print(f"Error classifying: {e}")

def broadcast(cfg: SwarmConfig, message: str, include_nonmonitored: bool, dry_run: bool) -> None:
    if not message.strip():
        raise ValueError("broadcast message must not be empty")
    payload = f"broadcast: {message.strip()}"
    sent = 0
    for pane in cfg.panes:
        if not pane.agent:
            continue
        if not include_nonmonitored and not pane.monitor:
            continue
        target = f"{cfg.session_name}:{pane.pane}"
        if dry_run:
            print(f"would broadcast to {target} ({pane.title})")
            sent += 1
            continue
        subprocess.run([str(ROOT_DIR / "tmux-send"), target, payload], check=True, text=True)
        print(f"broadcast to {target} ({pane.title})")
        sent += 1
    if sent == 0:
        scope = "all panes" if include_nonmonitored else "monitored panes"
        raise ValueError(f"no {scope} matched for broadcast")


def setup_monitors(cfg: SwarmConfig, dry_run: bool) -> None:
    """Start monitors, set pane titles, and run agent commands. Run after setup_grid or tmuxp load."""
    for pane in cfg.panes:
        if pane.monitor:
            ensure_monitor(cfg, pane.pane, pane.agent, dry_run)
    if not dry_run:
        time.sleep(0.2)
    for pane in cfg.panes:
        ensure_title(cfg, pane.pane, pane.title, dry_run)
        ensure_command(cfg, pane.pane, pane.title, pane.command, dry_run)
    write_runtime_map(cfg)
    write_self_awareness_text(cfg)


def apply(cfg: SwarmConfig, dry_run: bool, skip_grid: bool = False) -> None:
    if not skip_grid:
        setup_grid(cfg, dry_run)
    setup_monitors(cfg, dry_run)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
        print(f"wrote self-awareness note to {cfg.self_awareness_path}")
    print(f"{'Planned' if dry_run else 'Applied'} swarm for {cfg.session_name}")
    print()
    print(f"  Status: python {SWARM_CLI} status {cfg.path} --brief")
    print(f"  Watch:  python {SWARM_CLI} status {cfg.path} --brief -w")
    print()


def status_lines(cfg: SwarmConfig, brief: bool = False) -> list[str]:
    lines: list[str] = []
    session_exists = run("tmux", "has-session", "-t", f"={cfg.session_name}", check=False).returncode == 0
    existing_windows = run("tmux", "list-windows", "-t", cfg.session_name, "-F", "#{window_name}", check=False).stdout.splitlines() if session_exists else []
    actual_count = sum(_window_pane_count(cfg.session_name, w.window_name) for w in cfg.windows if w.window_name in existing_windows)
    session_ok = session_exists and all(w.window_name in existing_windows for w in cfg.windows)
    if brief:
        lines.append(f"{cfg.session_name} panes={actual_count}/{cfg.pane_count}" if session_ok else f"{cfg.session_name} missing")
    else:
        lines.append(f"session={cfg.session_name} exists={'yes' if session_ok else 'no'} panes={actual_count}/{cfg.pane_count}")
    if not session_ok:
        return lines
    brief_rows: list[tuple[str, str, str, str]] = []
    for pane in cfg.panes:
        target = f"{cfg.session_name}:{pane.pane}"
        proc = run("tmux", "list-panes", "-t", target, check=False)
        if proc.returncode != 0:
            lines.append(f"{target} missing")
            continue
        if pane.monitor:
            mon = _query_monitor(cfg, pane.pane)
            state_str = mon.get('state', 'unreachable')
            monitor = state_str
        else:
            monitor = "off"
        babysit_note = ""
        if pane.babysit.enabled:
            babysit_note = _format_babysit_note(cfg, pane.pane)
        if brief:
            brief_rows.append((target, pane.title, monitor, babysit_note or "off"))
        else:
            command = pane_current_command(cfg, pane.pane)
            babysit_val = ("on " + babysit_note) if pane.babysit.enabled and babysit_note else ("on" if pane.babysit.enabled else "off")
            lines.append(f"{target} title={pane.title} cmd={command or '-'} monitor={monitor} babysit={babysit_val}")
    if brief_rows:
        widths = [max(len(row[i]) for row in brief_rows) for i in range(4)]
        for row in brief_rows:
            lines.append("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip())
    return lines


def _format_babysit_note(cfg: SwarmConfig, pane: str) -> str:
    path = babysit_state_path(cfg, pane)
    if not path.exists():
        if not babysit_pid_path(cfg, pane).exists():
            return "stopped"
        return "restart-needed"
    try:
        data = json.loads(path.read_text())
    except Exception:
        return "?"
    now = int(time.time())
    next_poll_at = int(data.get("next_poll_at") or 0)
    last_monitor_state = str(data.get("last_monitor_state") or "").strip()
    next_force_at = int(data.get("next_force_nudge_at") or 0)
    parts: list[str] = []
    if next_poll_at > 0:
        parts.append(f"next={max(0, next_poll_at - now)}s")
    if next_force_at > 0 and last_monitor_state in {"unknown", "working", "error"}:
        parts.append(f"force={max(0, next_force_at - now)}s")
    if not parts:
        return "?"
    return ", ".join(parts)


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


def av_usage_lines(report: dict, recent_minutes: int = 0, title: str | None = None) -> list[str]:
    """Return a tabular, watch-friendly view of the av-usage report."""
    lines: list[str] = []
    if title:
        lines.append(title)

    for period in ("today", "week"):
        pinfo = report.get(period, {}) or {}
        pdate = pinfo.get("date") or f"{pinfo.get('from', '')} - {pinfo.get('to', '')}"
        lines.append(f"  {period}: {pdate}")

        bya = pinfo.get("by_agent", {}) or {}
        if isinstance(bya, dict) and "error" in bya:
            lines.append(f"    error: {bya['error']}")
            lines.append("")
            continue

        if not bya:
            lines.append("    (no data)")
            lines.append("")
            continue

        rows = []
        total_toks = 0
        total_cost = 0.0
        for ag in sorted(bya.keys()):
            v = bya[ag] or {}
            toks = (
                v.get("input_tokens", 0)
                + v.get("output_tokens", 0)
                + v.get("cache_creation_tokens", 0)
                + v.get("cache_read_tokens", 0)
            )
            cost = float(v.get("cost", 0))
            rows.append((ag, toks, cost))
            total_toks += toks
            total_cost += cost

        if not rows:
            lines.append("    (no data)")
            lines.append("")
            continue

        # column widths
        agent_w = max(len("Agent"), max(len(r[0]) for r in rows))
        toks_w = max(len("Tokens"), max(len(f"{r[1]:,}") for r in rows), len(f"{total_toks:,}"))
        cost_w = max(len("Cost"), max(len(f"${r[2]:.4f}") for r in rows), len(f"${total_cost:.4f}"))

        # header
        lines.append(f"  {'Agent'.ljust(agent_w)}  {'Tokens'.rjust(toks_w)}  {'Cost'.rjust(cost_w)}")
        lines.append(f"  {'-' * agent_w}  {'-' * toks_w}  {'-' * cost_w}")

        for ag, toks, cost in rows:
            lines.append(
                f"  {ag.ljust(agent_w)}  {f'{toks:,}'.rjust(toks_w)}  {f'${cost:.4f}'.rjust(cost_w)}"
            )

        lines.append(f"  {'-' * agent_w}  {'-' * toks_w}  {'-' * cost_w}")
        lines.append(
            f"  {'TOTAL'.ljust(agent_w)}  {f'{total_toks:,}'.rjust(toks_w)}  {f'${total_cost:.4f}'.rjust(cost_w)}"
        )
        lines.append("")

    if recent_minutes > 0:
        # fresh fetch for accuracy (cheap)
        from common import get_agentsview_recent_tokens
        eff = report.get("agents") or []
        rec = get_agentsview_recent_tokens(recent_minutes, agents=eff)
        lines.append(
            f"  recent {recent_minutes}m tokens: {rec.get('total_tokens', 0):,} ({rec.get('events', 0)} events)"
        )

    return lines


def print_av_usage(report: dict, recent_minutes: int = 0, title: str | None = None) -> None:
    lines = av_usage_lines(report, recent_minutes, title)
    print("\n".join(lines))


def watch_av_usage(agents: list[str] | None, recent_minutes: int = 0, interval: float = 30.0) -> None:
    """Watch loop for av-usage. Re-fetches each cycle so it works with polling."""
    from common import get_swarm_agentsview_report
    try:
        while True:
            report = get_swarm_agentsview_report(agents)
            eff = report.get("agents") or []
            if agents is not None:
                title = f"agentsview usage limited to swarm agents: {eff}"
            else:
                title = "agentsview global usage (all agents)"

            lines = av_usage_lines(report, recent_minutes, title)
            lines.insert(0, f"watch interval={interval:.1f}s updated={time.strftime('%H:%M:%S')}")
            sys.stdout.write("\x1b[H\x1b[2J")
            sys.stdout.write("\n".join(lines))
            sys.stdout.write("\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        return
