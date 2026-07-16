#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shlex
from datetime import datetime
import subprocess
import sys
import time
import json

try:
    from .common import (
        AGENT_STATS_CMD,
        ROOT_DIR,
        SHELL_NAMES,
        SWARM_CLI,
        SwarmConfig,
        WindowSpec,
        write_runtime_map,
    )

    from .babysitctl import (
        load_spec as load_babysit_spec,
        pid_path as babysit_pid_path,
        spec_path as babysit_spec_path,
        state_path as babysit_state_path,
        process_running as babysit_process_running,
        desired_spec as babysit_desired_spec,
    )
except ImportError:
    # direct script fallback
    from common import (
        AGENT_STATS_CMD,
        ROOT_DIR,
        SHELL_NAMES,
        SWARM_CLI,
        SwarmConfig,
        WindowSpec,
        write_runtime_map,
    )

    from babysitctl import (
        load_spec as load_babysit_spec,
        pid_path as babysit_pid_path,
        spec_path as babysit_spec_path,
        state_path as babysit_state_path,
        process_running as babysit_process_running,
        desired_spec as babysit_desired_spec,
    )


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
                "The grid layout cannot be safely mutated on an existing session. "
                "Run `stop` first (or `babysit stop` + kill the session) and then re-start, "
                "or use `tmuxp load` + `start --skip-grid` for more flexible grid management."
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
    try:
        proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True, timeout=3)
        return '"state"' in proc.stdout
    except subprocess.TimeoutExpired:
        return False




def _query_monitor(cfg: SwarmConfig, pane: str) -> dict:
    sock = socket_path(cfg, pane)
    try:
        proc = subprocess.run(["bash", "-lc", f"printf 'status' | nc -U {sock!s} 2>/dev/null"], text=True, capture_output=True, timeout=3)
        if proc.returncode != 0 or '"state"' not in proc.stdout:
            return {'state': 'unreachable'}
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {'state': 'unparseable'}
    except subprocess.TimeoutExpired:
        return {'state': 'unreachable'}


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
    raw = run("tmux", "display-message", "-p", "-t", f"{cfg.session_name}:{pane}", "#{pane_current_command}").stdout.strip()
    if not raw:
        return ""
    # Node.js (and some other) wrappers often report the interpreter (node/python)
    # instead of the tool name (codex, etc.). Try to resolve a friendlier name.
    if raw in ("node", "python", "python3", "bun", "deno"):
        pid = run("tmux", "display-message", "-p", "-t", f"{cfg.session_name}:{pane}", "#{pane_pid}").stdout.strip()
        if pid and pid.isdigit():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    parts = [p.decode("utf-8", errors="ignore") for p in f.read().split(b"\0") if p]
                # Look for known tool names in the arguments (skip the interpreter itself)
                for arg in parts[1:]:
                    a = arg.lower()
                    if "codex" in a:
                        return "codex"
                    if "claude" in a and "code" in a:
                        return "claude"
                    if "gemini" in a:
                        return "gemini"
                    if a.endswith("codex.js"):
                        return "codex"
                # Fallback: first non-empty non-interpreter basename
                for arg in parts[1:]:
                    base = os.path.basename(arg)
                    if base and base not in ("node", "python", "python3", "bun", "deno"):
                        return base
            except Exception:
                pass
    return raw


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



def capture_pane(cfg: SwarmConfig, pane: str) -> None:
    target = f"{cfg.session_name}:{pane}"
    proc = subprocess.run(["tmux", "capture-pane", "-t", target, "-p"], text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"could not capture {target}")
        return
    print(f"--- Capture {target} ---")
    print(proc.stdout)

def broadcast(cfg: SwarmConfig, message: str, include_nonmonitored: bool, dry_run: bool, via_log: bool = False) -> None:
    if not message.strip():
        raise ValueError("broadcast message must not be empty")
    sent = 0
    matching_panes = []
    for pane in cfg.panes:
        if not pane.agent:
            continue
        if not include_nonmonitored and not pane.monitor:
            continue
        matching_panes.append(pane)
    if via_log:
        if dry_run:
            for pane in matching_panes:
                target = f"{cfg.session_name}:{pane.pane}"
                print(f"would log-broadcast to {target} ({pane.title})")
                sent += 1
        else:
            try:
                from .common import log_broadcast
            except ImportError:
                from common import log_broadcast
            log_broadcast(cfg.session_name, message, sender="cli broadcast")
            for pane in matching_panes:
                target = f"{cfg.session_name}:{pane.pane}"
                print(f"log-broadcast to {target} ({pane.title})")
                sent += 1
    else:
        payload = message.strip()
        # Keep broadcast payloads literal. If a future label/prefix is added,
        # do not alter slash commands like "/clear".
        for pane in matching_panes:
            target = f"{cfg.session_name}:{pane.pane}"
            if dry_run:
                print(f"would tmux-broadcast to {target} ({pane.title})")
                sent += 1
                continue
            subprocess.run([str(ROOT_DIR / "tmux-send"), "--no-prefix", target, payload], check=True, text=True)
            print(f"tmux-broadcast to {target} ({pane.title})")
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


def start(cfg: SwarmConfig, dry_run: bool, skip_grid: bool = False) -> None:
    if not dry_run:
        try:
            from .common import init_comms_db
        except ImportError:
            from common import init_comms_db
        init_comms_db(cfg.session_name)
    if not skip_grid:
        setup_grid(cfg, dry_run)
    setup_monitors(cfg, dry_run)
    # Ensure base comms/IO workers (the single loop per pane) are running.
    # Babysit prompt group is managed separately via 'aiswarm babysit start'.
    try:
        from . import babysitctl
    except ImportError:
        import babysitctl
    babysitctl.ensure_workers(cfg, dry_run)
    try:
        from . import init as swarm_init
    except ImportError:
        import init as swarm_init
    agents_md = swarm_init.resolve_agents_md(cfg.path)
    if agents_md is not None:
        swarm_init.write_agents_block(agents_md, cfg.session_name, dry_run=dry_run)
    if dry_run:
        print(f"wrote runtime map to {cfg.runtime_map_path}")
    print(f"{'Planned' if dry_run else 'Started'} swarm for {cfg.session_name}")
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

    if brief:
        headers = ["Target", "Title", "Agent", "Worker"]
        rows = []
    else:
        headers = ["Target", "Title", "Command", "Agent", "PID", "Comms HB", "Babysit", "Nudge HB", "Clear HB"]
        rows = []

    for pane in cfg.panes:
        target = f"{cfg.session_name}:{pane.pane}"
        proc = run("tmux", "list-panes", "-t", target, check=False)
        if proc.returncode != 0:
            if brief:
                rows.append((target, pane.title, "missing", "off"))
            else:
                rows.append((target, pane.title, "-", "missing", "-", "-", "off", "-", "-"))
            continue
        if pane.monitor:
            mon = _query_monitor(cfg, pane.pane)
            state_str = mon.get('state', 'unreachable')
            monitor = state_str
        else:
            monitor = "off"
        pid_val = "-"
        comms_hb = "-"
        babysit_val = "off"
        nudge_hb = "-"
        clear_hb = "-"
        brief_val = "off"

        if pane.babysit.enabled or pane.comms:
            # 1. Determine active mode from running spec (fallback to configured mode)
            active_mode = None
            note = ""
            spec = load_babysit_spec(babysit_spec_path(cfg, pane.pane))
            if spec:
                has_prompts = bool(spec.get("long_prompt") or spec.get("short_prompt"))
                active_mode = "babysit" if has_prompts else "comms"
            else:
                active_mode = "babysit" if pane.babysit.enabled else "comms"

            # 2. Check for drift / babysit not started
            if spec:
                if pane.babysit.enabled:
                    di, dc, dlp, dsp = (
                        pane.babysit.interval_secs,
                        pane.babysit.clear_every,
                        pane.babysit.long_prompt,
                        pane.babysit.short_prompt,
                    )
                    dlp_f = pane.babysit.long_prompt_file.name if pane.babysit.long_prompt_file else ""
                    dsp_f = pane.babysit.short_prompt_file.name if pane.babysit.short_prompt_file else ""
                    dvl = pane.babysit.via_log
                else:
                    di, dc, dlp, dsp, dlp_f, dsp_f, dvl = 5, 0, "", "", "", "", True

                try:
                    des = babysit_desired_spec(cfg, pane.pane, di, dc, dlp, dsp, dlp_f, dsp_f, dvl)
                    if spec != des:
                        if pane.babysit.enabled and active_mode == "comms":
                            note = "babysit not started"
                        else:
                            note = "drifted"
                except Exception:
                    note = "drifted"

            # 3. Check state file for next poll
            comms_hb_str = "-"
            nudge_hb_str = "-"
            state_file = babysit_state_path(cfg, pane.pane)
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text())
                    now = int(time.time())
                    next_poll_at = int(data.get("next_poll_at") or 0)
                    next_nudge_at = int(data.get("next_nudge_at") or 0)
                    if next_nudge_at == 0:
                        next_nudge_at = next_poll_at
                    if next_poll_at > 0:
                        delta_poll = max(0, next_poll_at - now)
                        comms_hb_str = "≤5s" if delta_poll <= 0 else f"{delta_poll}s"
                    if next_nudge_at > 0:
                        delta_nudge = max(0, next_nudge_at - now)
                        nudge_hb_str = "≤5s" if delta_nudge <= 0 else f"{delta_nudge}s"
                except Exception:
                    comms_hb_str = "?"
                    nudge_hb_str = "?"

            # 4. Check if PID file exists & check process running
            pid_file = babysit_pid_path(cfg, pane.pane)
            pid = None
            is_running = False
            proc_state = "stopped"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    is_running = babysit_process_running(pid)
                    proc_state = "running" if is_running else "stale"
                except (ValueError, OSError):
                    pass
            elif state_file.exists():
                # fallback for unit tests where state file is written but pid file is missing
                is_running = True
                proc_state = "running"

            if proc_state == "stopped":
                pid_val = "-"
                comms_hb = "-"
                brief_val = "stopped"
                if pane.babysit.enabled:
                    babysit_val = "stopped"
                else:
                    babysit_val = "off"
                nudge_hb = "-"
                clear_hb = "-"
            else:
                # 5. Format brief vs non-brief values
                pid_val = str(pid) if pid else "-"
                comms_hb = comms_hb_str

                if proc_state == "stale":
                    brief_val = "stale"
                    if pane.babysit.enabled:
                        babysit_val = "stale"
                    else:
                        babysit_val = "off"
                    nudge_hb = "-"
                    clear_hb = "-"
                else:
                    # running
                    hb_to_show = nudge_hb_str if pane.babysit.enabled and active_mode == "babysit" and note != "babysit not started" else comms_hb_str
                    if note:
                        brief_val = f"next={hb_to_show} ({note})" if hb_to_show != "-" else note
                    else:
                        brief_val = f"next={hb_to_show}" if hb_to_show != "-" else "running"

                    if pane.babysit.enabled:
                        if active_mode == "comms":
                            babysit_val = "not started"
                            nudge_hb = "-"
                            clear_hb = "-"
                        elif note == "drifted":
                            babysit_val = "drifted"
                            nudge_hb = "-"
                            clear_hb = "-"
                        else:
                            # active running
                            babysit_val = "on"
                            nudge_hb = nudge_hb_str
                            
                            # clear countdown
                            if spec:
                                clear_every = int(spec.get("clear_every") or 0)
                                if clear_every > 0:
                                    if state_file.exists():
                                        try:
                                            data = json.loads(state_file.read_text())
                                            ema = data.get("ema") or {}
                                            nudge_count = int(ema.get("nudge_count") or 0)
                                            rem = clear_every - (nudge_count % clear_every)
                                            clear_hb = str(rem)
                                        except Exception:
                                            pass
                    else:
                        babysit_val = "off"
                        nudge_hb = "-"
                        clear_hb = "-"

        if brief:
            rows.append((target, pane.title, monitor, brief_val))
        else:
            # Show the configured command from the YAML (what was requested),
            # not the live process name from tmux (which for node-based tools
            # like codex shows "node").
            command = pane.command or pane_current_command(cfg, pane.pane) or "-"
            rows.append((target, pane.title, command or "-", monitor, pid_val, comms_hb, babysit_val, nudge_hb, clear_hb))

    if rows:
        all_rows = [headers] + rows
        widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
        lines.append("")
        lines.append("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))).rstrip())
        lines.append("  ".join(("-" * widths[i]).ljust(widths[i]) for i in range(len(headers))).rstrip())
        for row in rows:
            lines.append("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))).rstrip())

        if not brief:
            lines.append("")
            lines.append("  Agent    = live state of the agent in the pane (from its monitor: idle/working/etc)")
            lines.append("  Comms HB = countdown to the next background worker loop check (messages + polling)")
            lines.append("  Babysit  = babysit prompt group status (on, off/not-started, drifted, stopped, stale)")
            lines.append("  Nudge HB = countdown to the next idle nudge check (babysit group only)")
            lines.append("  Clear HB = remaining nudges until next context clear (/clear)")
            lines.append("             Run `babysit start` / `babysit stop` to toggle the babysit prompt group.")

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
        try:
            from .common import get_agentsview_recent_tokens
        except ImportError:
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
    try:
        from .common import get_swarm_agentsview_report
    except ImportError:
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


def _kv(name: str, value) -> str:
    return f"{name}={json.dumps(value, separators=(',', ':'))}"


def _print_log_event(
    eid: int,
    ts: str,
    rec: str,
    snd: str | None,
    typ: str,
    pay: str,
    meta: str | None,
    **extra,
) -> None:
    parts = [
        _kv("id", eid),
        _kv("ts", ts),
        _kv("type", typ),
        _kv("from", snd or "-"),
        _kv("to", rec),
    ]
    for key, value in extra.items():
        parts.append(_kv(key, value))
    parts.append(_kv("payload", pay))
    if meta:
        try:
            parts.append(_kv("meta", json.loads(meta)))
        except json.JSONDecodeError:
            parts.append(_kv("meta", meta))
    print(" ".join(parts))
    print()


def print_log(cfg: SwarmConfig, pane: str | None = None, limit: int = 50, pending: bool = False) -> None:
    try:
        from .common import get_cursors, get_events, get_pending_events, get_pending_broadcasts
    except ImportError:
        from common import get_cursors, get_events, get_pending_events, get_pending_broadcasts
    curs = get_cursors(cfg.session_name)
    if curs:
        print("cursors:")
        for rec, lid in sorted(curs.items()):
            print(f"  {rec}: {lid}")
    else:
        print("cursors: (none)")
    print()
    if pending:
        if pane:
            pend = get_pending_events(cfg.session_name, pane)
            for eid, ts, snd, typ, pay, meta in pend:
                _print_log_event(eid, ts, pane, snd, typ, pay, meta)
            try:
                bpend = get_pending_broadcasts(cfg.session_name, pane)
                for eid, ts, snd, typ, pay, meta in bpend:
                    _print_log_event(eid, ts, pane, snd, typ, pay, meta, via="broadcast")
            except Exception:
                pass
        else:
            print("pending summary (use --pane for details):")
            try:
                bcasts = get_pending_events(cfg.session_name, "__broadcast__")
                print(f"  __broadcast__ pending: {len(bcasts)}")
            except Exception:
                pass
            print("  Run with --pane X.Y for per-pane pending")
    else:
        evs = get_events(cfg.session_name, pane, limit)
        if not evs:
            print("(no events)")
        for eid, ts, rec, snd, typ, pay, meta in evs:
            _print_log_event(eid, ts, rec, snd, typ, pay, meta)


def watch_log(cfg: SwarmConfig, pane: str | None = None, limit: int = 50, pending: bool = False, interval: float = 1.0) -> None:
    if not pending:
        try:
            from .common import get_events
        except ImportError:
            from common import get_events
        last_id = 0
        try:
            print(f"watch interval={interval:.1f}s session={cfg.session_name}")
            print()
            while True:
                evs = get_events(cfg.session_name, pane, limit)
                new = [ev for ev in evs if ev[0] > last_id]
                for eid, ts, rec, snd, typ, pay, meta in new:
                    _print_log_event(eid, ts, rec, snd, typ, pay, meta)
                    last_id = eid
                sys.stdout.flush()
                time.sleep(interval)
        except KeyboardInterrupt:
            return

    try:
        while True:
            sys.stdout.write("\x1b[H\x1b[2J")
            sys.stdout.write(f"watch interval={interval:.1f}s updated={time.strftime('%H:%M:%S')}\n\n")
            print_log(cfg, pane, limit, pending)
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        return
