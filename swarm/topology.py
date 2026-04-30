#!/usr/bin/env python3
from __future__ import annotations

import re
import shlex
from datetime import datetime
import subprocess
import sys
import time
import json

from common import AGENT_STATS_CMD, ROOT_DIR, SHELL_NAMES, SWARM_CLI, SwarmConfig, write_runtime_map, write_self_awareness_text

# Patterns tried per line in order; first match wins for that line.
# Returns list of {"label": str, "pct": int} dicts (pct = % remaining).
_LINE_PATTERNS = [
    # codex: "5h limit: [███] 100% left ..."  or  "Weekly limit: [███] 97% left ..."
    (re.compile(r'(\w+)\s+limit:.*?(\d+)%\s+left', re.IGNORECASE), 'labeled_left'),
    # generic "N% left"
    (re.compile(r'(\d+)%\s+left', re.IGNORECASE), 'pct_left'),
    # claude /usage: "12% used"
    (re.compile(r'(\d+)%\s+used', re.IGNORECASE), 'pct_used'),
    # hours: "4.2 / 5.0 hours"
    (re.compile(r'(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*hours', re.IGNORECASE), 'hours_used'),
    # gemini /stats: "0%  10:04 PM (24h)" — bare % followed by a clock = % used
    (re.compile(r'\b(\d+)%\s+\d{1,2}:\d{2}\s+(?:AM|PM)', re.IGNORECASE), 'pct_used'),
]
from babysitctl import pid_path as babysit_pid_path, state_path as babysit_state_path


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
    if run("tmux", "has-session", "-t", f"={cfg.session_name}", check=False).returncode != 0:
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


def _parse_reset_ts(s: str) -> int | None:
    """Parse a reset string to a Unix timestamp. Returns None if unparseable."""
    if not s:
        return None
    now = datetime.now()
    # strip timezone hint "(Europe/London)" etc — we work in local time
    s = re.sub(r'\s*\([^)]*\)', '', s).strip()

    # "02:49 on 31 Mar" or "07:37 on 3 Apr"
    m = re.match(r'(\d{1,2}):(\d{2})\s+on\s+(\d{1,2})\s+(\w+)', s)
    if m:
        hour, minute, day, mon = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        for yr in (now.year, now.year + 1):
            try:
                dt = datetime.strptime(f"{day} {mon} {yr} {hour}:{minute}", "%d %b %Y %H:%M")
                if dt.timestamp() > now.timestamp():
                    return int(dt.timestamp())
            except ValueError:
                pass

    # "Apr 5, 1pm" or "Apr 5, 1:30pm" or "Apr 5, 13:00"
    m = re.match(r'(\w+)\s+(\d{1,2}),?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', s, re.IGNORECASE)
    if m:
        mon, day = m.group(1), int(m.group(2))
        hour, minute = int(m.group(3)), int(m.group(4) or 0)
        ampm = (m.group(5) or '').lower()
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        for yr in (now.year, now.year + 1):
            try:
                dt = datetime.strptime(f"{day} {mon} {yr} {hour}:{minute}", "%d %b %Y %H:%M")
                if dt.timestamp() > now.timestamp():
                    return int(dt.timestamp())
            except ValueError:
                pass

    return None


def _usage_cache_path(cfg: SwarmConfig, pane: str):
    return cfg.runtime_dir / f"usage-{pane.replace('.', '-')}.json"


def _parse_usage_from_text(text: str) -> list[dict]:
    """Return list of {label, pct, reset} dicts parsed from pane text."""
    _reset = re.compile(r'resets\s+(.+)', re.IGNORECASE)
    limits: list[dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        entry: dict | None = None
        for pat, kind in _LINE_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            try:
                if kind == 'labeled_left':
                    entry = {"label": m.group(1).lower(), "pct": int(m.group(2))}
                elif kind == 'pct_left':
                    entry = {"label": "", "pct": int(m.group(1))}
                elif kind == 'pct_used':
                    entry = {"label": "", "pct": max(0, 100 - int(m.group(1)))}
                elif kind == 'hours_used':
                    used, total = float(m.group(1)), float(m.group(2))
                    if total > 0:
                        entry = {"label": "", "pct": round((1.0 - used / total) * 100)}
            except (ValueError, ZeroDivisionError):
                pass
            if entry:
                # check same line then next line for reset date
                search_lines = [line] + ([lines[i + 1]] if i + 1 < len(lines) else [])
                reset = ""
                for sl in search_lines:
                    rm = _reset.search(sl)
                    if rm:
                        reset = rm.group(1).strip().rstrip('│╯╰ ')
                        # strip trailing ) from box-drawing if parens unbalanced
                        while reset.endswith(')') and reset.count('(') < reset.count(')'):
                            reset = reset[:-1].rstrip()
                        break
                entry["reset"] = reset
                entry["reset_ts"] = _parse_reset_ts(reset) or 0
                limits.append(entry)
                break
    # If any labeled limits exist, drop unlabeled ones (avoids status-bar noise)
    labeled = [l for l in limits if l["label"]]
    return labeled if labeled else limits


def _format_limits(limits: list[dict]) -> str:
    parts = []
    for lim in limits:
        s = f"{lim['label']}:{lim['pct']}%" if lim['label'] else f"{lim['pct']}%"
        reset = lim.get('reset', '').strip()
        if reset:
            s += f" (resets {reset})"
        parts.append(s)
    return "  ".join(parts)


def _write_usage_cache(cfg: SwarmConfig, pane: str, limits: list[dict]) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    _usage_cache_path(cfg, pane).write_text(json.dumps({"limits": limits, "ts": int(time.time())}) + "\n")


def _read_usage_cache(cfg: SwarmConfig, pane: str) -> list[dict] | None:
    path = _usage_cache_path(cfg, pane)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("limits") or None
    except Exception:
        return None


def _query_monitor(cfg: SwarmConfig, pane: str) -> dict:
    sock = socket_path(cfg, pane)
    proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True)
    if proc.returncode != 0 or '"state"' not in proc.stdout:
        result: dict = {'state': 'unreachable'}
    else:
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {'state': 'unparseable'}
    if 'usage_limits' not in result:
        cached = _read_usage_cache(cfg, pane)
        if cached is not None:
            result['usage_limits'] = cached
            result['usage_pct'] = min(lim['pct'] for lim in cached)
    return result


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
    subprocess.run(["tmux", "send-keys", "-t", f"{cfg.session_name}:{pane}", "-l", "--", command], check=True, text=True)
    time.sleep(0.1)
    subprocess.run(["tmux", "send-keys", "-t", f"{cfg.session_name}:{pane}", "C-m"], check=True, text=True)


def probe_usage(cfg: SwarmConfig, dry_run: bool) -> None:
    targets = []
    for pane in cfg.panes:
        if not pane.monitor or not pane.agent:
            continue
        cmd = AGENT_STATS_CMD.get(pane.agent)
        if not cmd:
            print(f"no stats command known for {pane.agent} ({cfg.session_name}:{pane.pane}), skipping")
            continue
        target = f"{cfg.session_name}:{pane.pane}"
        if dry_run:
            print(f"would send {cmd!r} to {target} ({pane.title})")
        else:
            subprocess.run([str(ROOT_DIR / "tmux-send"), target, cmd], check=True, text=True)
        targets.append((pane, target, cmd))

    if not targets:
        print("no monitored panes with a known stats command")
        return

    if dry_run:
        return

    time.sleep(2)  # wait for CLIs to render their response
    for pane, target, cmd in targets:
        proc = subprocess.run(["tmux", "capture-pane", "-t", target, "-p"], text=True, capture_output=True)
        if pane.agent == "claude":
            subprocess.run(["tmux", "send-keys", "-t", target, "Escape"], check=False)
        limits = _parse_usage_from_text(proc.stdout)
        if limits:
            _write_usage_cache(cfg, pane.pane, limits)
            print(f"{target} ({pane.title}): {_format_limits(limits)}")
        else:
            print(f"{target} ({pane.title}): {cmd!r} sent (no usage pattern matched)")


def broadcast(cfg: SwarmConfig, message: str, include_nonmonitored: bool, dry_run: bool) -> None:
    if not message.strip():
        raise ValueError("broadcast message must not be empty")
    payload = f"broadcast: {message.strip()}"
    sent = 0
    for pane in cfg.panes:
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
    write_runtime_map(cfg)
    write_self_awareness_text(cfg)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
        print(f"wrote self-awareness note to {cfg.self_awareness_path}")
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
    session_exists = run("tmux", "has-session", "-t", f"={cfg.session_name}", check=False).returncode == 0
    window_exists = run("tmux", "list-windows", "-t", cfg.session_name, check=False).stdout.find(cfg.window_name) != -1 if session_exists else False
    actual_count = pane_count(cfg) if window_exists else 0
    if brief:
        lines.append(f"{cfg.session_name}:{cfg.window_name} panes={actual_count}/{cfg.pane_count}" if window_exists else f"{cfg.session_name}:{cfg.window_name} missing")
    else:
        lines.append(f"session={cfg.session_name} window={cfg.window_name} exists={'yes' if window_exists else 'no'} panes={actual_count}/{cfg.pane_count}")
    if not window_exists:
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
            limits = mon.get('usage_limits')
            if limits:
                usage_str = " " + _format_limits(limits)
            elif mon.get('usage_pct') is not None:
                usage_str = f" {mon['usage_pct']}%"
            else:
                usage_str = ""
            monitor = state_str + usage_str
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
