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
from pathlib import Path

try:
    from .common import (
        AGENT_STATS_CMD,
        ROOT_DIR,
        SHELL_NAMES,
        SWARM_CLI,
        SwarmConfig,
        WindowSpec,
        query_monitor_socket,
        query_monitor_state,
        write_runtime_map,
    )

    from .babysitctl import (
        load_spec as load_babysit_spec,
        pid_path as babysit_pid_path,
        spec_path as babysit_spec_path,
        state_path as babysit_state_path,
        process_running as babysit_process_running,
        desired_spec as babysit_desired_spec,
        supervisor_pid_path,
    )
    from .tasksctl import (
        is_group_enabled as tasks_group_enabled,
        list_candidate_tasks,
        task_categories,
        worker_state_path,
    )
    from .session_ids import (
        mint_launch_command,
        resume_launch_command,
        make_record,
        load_records,
        save_records,
        refresh_records,
        merge_record,
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
        query_monitor_socket,
        query_monitor_state,
        write_runtime_map,
    )

    from babysitctl import (
        load_spec as load_babysit_spec,
        pid_path as babysit_pid_path,
        spec_path as babysit_spec_path,
        state_path as babysit_state_path,
        process_running as babysit_process_running,
        desired_spec as babysit_desired_spec,
        supervisor_pid_path,
    )
    from tasksctl import (
        is_group_enabled as tasks_group_enabled,
        list_candidate_tasks,
        task_categories,
        worker_state_path,
    )
    from session_ids import (
        mint_launch_command,
        resume_launch_command,
        make_record,
        load_records,
        save_records,
        refresh_records,
        merge_record,
    )


def _title_cats(pane) -> str:
    return f"{pane.title} [{','.join(pane.categories)}]" if pane.categories else pane.title


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

    # Plain interactive bash: no .bashrc PS1 (user@host) before agent CLI takes over.
    # Single argv for tmux [shell-command].
    pane_shell = "env PS1='$ ' bash --norc --noprofile"

    if not win_exists:
        if dry_run:
            print(f"would create window {target}")
        else:
            if is_first:
                # first window was already created with the session
                run("tmux", "rename-window", "-t", f"{session_name}:0", win.window_name)
            else:
                run("tmux", "new-window", "-t", session_name, "-n", win.window_name, pane_shell)
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
        run("tmux", "split-window", "-t", f"{target}.0", pane_shell)
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
            run(
                "tmux",
                "new-session",
                "-d",
                "-s",
                cfg.session_name,
                "-n",
                cfg.windows[0].window_name,
                "env PS1='$ ' bash --norc --noprofile",
            )
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
    return "state" in query_monitor_socket(session_name, pane)




def _query_monitor(cfg: SwarmConfig, pane: str) -> dict:
    data = query_monitor_socket(cfg.session_name, pane)
    if not data:
        return {'state': 'unreachable'}
    if 'state' not in data and 'status' not in data:
        return {'state': 'unparseable'}
    return data


def monitor_state(cfg: SwarmConfig, pane: str) -> str:
    return query_monitor_state(cfg.session_name, pane)


def ensure_monitor(cfg: SwarmConfig, pane: str, agent: str, dry_run: bool) -> None:
    if socket_ready(cfg.session_name, pane):
        return
    if dry_run:
        print(f"would attach monitor for {cfg.session_name}:{pane} ({agent})")
        return
    subprocess.run([str(ROOT_DIR / "attach.sh"), f"{cfg.session_name}:{pane}", agent], check=True, text=True)


def pane_pid(cfg: SwarmConfig, pane: str) -> int | None:
    proc = run(
        "tmux",
        "display-message",
        "-p",
        "-t",
        f"{cfg.session_name}:{pane}",
        "#{pane_pid}",
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def collect_pane_pids(cfg: SwarmConfig) -> dict[str, int]:
    out: dict[str, int] = {}
    for pane in cfg.panes:
        pid = pane_pid(cfg, pane.pane)
        if pid is not None:
            out[pane.pane] = pid
    return out


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


def ensure_command(cfg: SwarmConfig, pane: str, title: str, command: str, dry_run: bool) -> bool:
    command = shell_prefixed_command(title, command)
    if dry_run:
        print(f"would start command in {cfg.session_name}:{pane}: {command}")
        return True
    current = pane_current_command(cfg, pane)
    if current and current not in SHELL_NAMES:
        return False
    subprocess.run([str(ROOT_DIR / "tmux-send"), "--no-prefix", f"{cfg.session_name}:{pane}", command], check=True, text=True)
    return True



def capture_pane_text(cfg: SwarmConfig, pane: str) -> str | None:
    target = f"{cfg.session_name}:{pane}"
    proc = subprocess.run(["tmux", "capture-pane", "-t", target, "-p"], text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def capture_pane(cfg: SwarmConfig, pane: str) -> None:
    target = f"{cfg.session_name}:{pane}"
    text = capture_pane_text(cfg, pane)
    if text is None:
        print(f"could not capture {target}")
        return
    print(f"--- Capture {target} ---")
    print(text)


def wait_pane(
    cfg: SwarmConfig,
    pane: str,
    *,
    timeout: float = 120.0,
    interval: float = 1.0,
    stable: float | None = None,
) -> int:
    """Block until monitor idle, or until capture-pane text is unchanged for `stable` seconds.

    Prints one line. Returns 0 on success, 1 on timeout, 2 on bad pane.
    """
    if interval <= 0:
        raise ValueError("--interval must be > 0")
    if timeout < 0:
        raise ValueError("--timeout must be >= 0")
    if stable is not None and stable <= 0:
        raise ValueError("--stable must be > 0")
    if pane not in {p.pane for p in cfg.panes}:
        print(f"unknown pane {pane}", file=sys.stderr)
        return 2
    deadline = None if timeout == 0 else time.monotonic() + timeout
    last_text: str | None = None
    stable_since: float | None = None
    state = "unknown"
    while True:
        now = time.monotonic()
        if stable is not None:
            text = capture_pane_text(cfg, pane)
            if text is None:
                state = "unknown"
                last_text = None
                stable_since = None
            elif text != last_text:
                last_text = text
                stable_since = now
                state = "working"
            elif stable_since is not None and now - stable_since >= stable:
                print(f"{pane} stable")
                return 0
            else:
                state = "working"
        else:
            state = query_monitor_state(cfg.session_name, pane)
            if state == "idle":
                print(f"{pane} idle")
                return 0
        if deadline is not None and now >= deadline:
            print(f"{pane} timeout {state}")
            return 1
        sleep_for = interval
        if deadline is not None:
            sleep_for = min(sleep_for, max(0.0, deadline - time.monotonic()))
        time.sleep(sleep_for)

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
            log_broadcast(cfg.session_name, message, include_nonmonitored=include_nonmonitored, sender="cli broadcast")
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


def setup_monitors(cfg: SwarmConfig, dry_run: bool, resume: bool = False) -> None:
    """Start monitors, set pane titles, and run agent commands. Run after setup_grid or tmuxp load."""
    for pane in cfg.panes:
        if pane.monitor:
            ensure_monitor(cfg, pane.pane, pane.agent, dry_run)
    if not dry_run:
        time.sleep(0.2)
    records = load_records(cfg)
    for pane in cfg.panes:
        ensure_title(cfg, pane.pane, pane.title, dry_run)
        command = pane.command
        if resume:
            alt = resume_launch_command(pane.agent, records.get(pane.pane))
            if alt:
                command = alt
                print(f"{pane.pane} resume -> {command}")
        minted = None
        mint_source = ""
        if pane.agent:
            command, minted, mint_source = mint_launch_command(pane.agent, command)
        launched = ensure_command(cfg, pane.pane, pane.title, command, dry_run)
        if minted and (dry_run or launched):
            records[pane.pane] = merge_record(
                records.get(pane.pane),
                make_record(pane.pane, pane.agent, minted, mint_source or "minted"),
            )
    if records:
        save_records(cfg, records)
    if not dry_run:
        time.sleep(0.3)
        refresh_records(cfg, collect_pane_pids(cfg))
    write_runtime_map(cfg)


def start(cfg: SwarmConfig, dry_run: bool, skip_grid: bool = False, resume: bool = False) -> None:
    for pane in cfg.panes:
        if pane.alias_warning:
            print(f"{pane.pane}: {pane.alias_warning}", file=sys.stderr)
        if pane.command_alias:
            print(f"{pane.pane} {pane.command_alias} -> {pane.command}")
    if not dry_run:
        try:
            from .common import init_comms_db
        except ImportError:
            from common import init_comms_db
        init_comms_db(cfg.session_name)
    if not skip_grid:
        setup_grid(cfg, dry_run)
    setup_monitors(cfg, dry_run, resume=resume)
    # Ensure the one session worker (multiplexed comms/IO for every pane) is running.
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


def category_lines(cfg: SwarmConfig, states: dict[str, str]) -> list[str]:
    """Per-category rollup: panes, idle panes, pending any-messages, open cat: tasks."""
    try:
        from .common import get_pending_any
    except ImportError:
        from common import get_pending_any
    panes: dict[str, list[str]] = {}
    for p in cfg.panes:
        for c in p.categories:
            panes.setdefault(c, []).append(p.pane)
    msgs: dict[str, int] = {}
    for *_, meta in get_pending_any(cfg.session_name):
        try:
            cat = (json.loads(meta) if meta else {}).get("category")
        except (TypeError, ValueError):
            cat = None
        if cat:
            msgs[cat] = msgs.get(cat, 0) + 1
    tasks: dict[str, int] = {}
    if tasks_group_enabled(cfg):
        try:
            for t in list_candidate_tasks(cfg, unassigned_only=False):
                for c in task_categories(t):
                    tasks[c] = tasks.get(c, 0) + 1
        except Exception:
            pass
    names = sorted(set(panes) | set(msgs) | set(tasks))
    if not names:
        return []
    rows = [("Category", "Panes", "Idle", "Msgs", "Tasks")]
    for c in names:
        ps = panes.get(c, [])
        idle = sum(1 for p in ps if states.get(p) == "idle")
        rows.append((c, ",".join(ps) or "-", str(idle), str(msgs.get(c, 0)), str(tasks.get(c, 0))))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    out = ["", "Categories (Msgs = pending any-messages, Tasks = open cat: tasks)"]
    out += ["  ".join(r[i].ljust(widths[i]) for i in range(5)).rstrip() for r in rows]
    return out


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
        headers = [
            "Target", "Title", "Command", "Agent", "PID", "Comms HB",
            "Babysit", "Nudge HB", "Clear HB", "Tasks", "Tasks HB",
        ]
        rows = []

    tasks_enabled = tasks_group_enabled(cfg)
    tasks_pid_file = supervisor_pid_path(cfg)
    tasks_worker = "stopped"
    if tasks_pid_file.exists():
        try:
            tasks_pid = int(tasks_pid_file.read_text().strip())
            tasks_worker = "on" if babysit_process_running(tasks_pid) else "stale"
        except (OSError, ValueError):
            tasks_worker = "stale"
    tasks_hb = "?"
    if tasks_enabled and tasks_worker == "on":
        try:
            data = json.loads(worker_state_path(cfg).read_text())
            delta = max(0, int(data.get("next_poll_at") or 0) - int(time.time()))
            tasks_hb = "≤1s" if delta <= 0 else f"{delta}s"
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            tasks_hb = "?"

    states: dict[str, str] = {}
    for pane in cfg.panes:
        target = f"{cfg.session_name}:{pane.pane}"
        proc = run("tmux", "list-panes", "-t", target, check=False)
        if proc.returncode != 0:
            if brief:
                rows.append((target, _title_cats(pane), "missing", "off"))
            else:
                rows.append(
                    (target, _title_cats(pane), "-", "missing", "-", "-", "off", "-", "-",
                     "off", "-")
                )
            continue
        if pane.monitor:
            mon = _query_monitor(cfg, pane.pane)
            state_str = mon.get('state', 'unreachable')
            monitor = state_str
        else:
            monitor = "off"
        states[pane.pane] = monitor
        pid_val = "-"
        comms_hb = "-"
        babysit_val = "off"
        nudge_hb = "-"
        clear_hb = "-"
        brief_val = "off"
        tasks_val = "off"
        pane_tasks_hb = "-"
        if pane.tasks_enabled and tasks_enabled:
            tasks_val = tasks_worker
            pane_tasks_hb = tasks_hb if tasks_worker == "on" else "-"

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
                            if spec and spec.get("simulate"):
                                babysit_val += " (simulate)"
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
            rows.append((target, _title_cats(pane), monitor, brief_val))
        else:
            # Show the configured command from the YAML (what was requested),
            # not the live process name from tmux (which for node-based tools
            # like codex shows "node").
            command = pane.command or pane_current_command(cfg, pane.pane) or "-"
            rows.append(
                (target, _title_cats(pane), command or "-", monitor, pid_val, comms_hb,
                 babysit_val, nudge_hb, clear_hb, tasks_val, pane_tasks_hb)
            )

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
            lines.append("  Tasks    = task-dispatch group state for this pane")
            lines.append("  Tasks HB = countdown to the next claim/chase dispatcher pass")
            lines.append("             Run `babysit start` / `babysit stop` to toggle the babysit prompt group.")

    lines.extend(category_lines(cfg, states))
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
        from .common import (get_cursors, get_events, get_pending_any,
                             get_pending_broadcasts, get_pending_events)
    except ImportError:
        from common import (get_cursors, get_events, get_pending_any,
                            get_pending_broadcasts, get_pending_events)
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
            found = False
            for pane_spec in cfg.panes:
                for eid, ts, snd, typ, pay, meta in get_pending_events(cfg.session_name, pane_spec.pane):
                    _print_log_event(eid, ts, pane_spec.pane, snd, typ, pay, meta)
                    found = True
                try:
                    for eid, ts, snd, typ, pay, meta in get_pending_broadcasts(cfg.session_name, pane_spec.pane):
                        _print_log_event(eid, ts, pane_spec.pane, snd, typ, pay, meta, via="broadcast")
                        found = True
                except Exception:
                    pass
            for eid, ts, snd, typ, pay, meta in get_pending_any(cfg.session_name):
                try:
                    cat = (json.loads(meta) if meta else {}).get("category")
                except (TypeError, ValueError):
                    cat = None
                _print_log_event(eid, ts, f"__any__:{cat}" if cat else "__any__", snd, typ, pay, meta)
                found = True
            if not found:
                print("(no pending events)")
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


def inspect_swarms(runtime_root: Path | None = None) -> list[dict]:
    if runtime_root is None:
        runtime_root = Path("/tmp/nudge-swarm")
    swarms: list[dict] = []
    if not runtime_root.exists():
        return swarms
    try:
        entries = sorted(runtime_root.iterdir())
    except OSError:
        return swarms

    for entry in entries:
        if not entry.is_dir():
            continue
        runtime_json = entry / "runtime.json"
        if not runtime_json.is_file():
            continue
        try:
            data = json.loads(runtime_json.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        session_name = data.get("session_name") or entry.name
        panes = data.get("panes") or {}
        pane_count = len(panes)

        # Check if tmux session exists
        res = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tmux_alive = (res.returncode == 0)

        # Check if session worker is running
        worker_pid_file = entry / "session_worker.pid"
        worker_alive = False
        if worker_pid_file.exists():
            try:
                pid = int(worker_pid_file.read_text().strip())
                os.kill(pid, 0)
                worker_alive = True
            except (OSError, ValueError):
                worker_alive = False

        if tmux_alive and worker_alive:
            status = "active"
            worker_status = "running"
        elif tmux_alive:
            status = "tmux-only"
            worker_status = "stopped"
        elif worker_alive:
            status = "worker-only"
            worker_status = "running"
        else:
            status = "inactive"
            worker_status = "stopped"

        swarms.append({
            "session_name": session_name,
            "status": status,
            "panes": pane_count,
            "worker": worker_status,
            "runtime_dir": str(entry),
        })

    order = {"active": 0, "tmux-only": 1, "worker-only": 2, "inactive": 3}
    swarms.sort(key=lambda s: (order.get(s["status"], 9), s["session_name"]))
    return swarms


def print_swarms(brief: bool = False, as_json: bool = False, runtime_root: Path | None = None) -> None:
    swarms = inspect_swarms(runtime_root)
    if as_json:
        print(json.dumps(swarms, indent=2))
        return
    if not swarms:
        print("no swarms found in /tmp/nudge-swarm")
        return
    if brief:
        for s in swarms:
            print(f"{s['session_name']} ({s['status']}, {s['panes']} panes)")
        return

    header = f"{'SWARM':<20} {'STATUS':<12} {'PANES':<8} {'WORKER':<10} {'RUNTIME_DIR'}"
    print(header)
    print("-" * len(header))
    for s in swarms:
        print(f"{s['session_name']:<20} {s['status']:<12} {s['panes']:<8} {s['worker']:<10} {s['runtime_dir']}")

