#!/usr/bin/env python3
"""Control plane for the session-level tasks dispatcher (not babysit)."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from .common import (
        ROOT_DIR,
        SwarmConfig,
        TasksSpec,
        get_pending_events,
        log_send,
        monitor_socket_path,
        write_runtime_map,
        write_self_awareness_text,
    )
except ImportError:
    from common import (
        ROOT_DIR,
        SwarmConfig,
        TasksSpec,
        get_pending_events,
        log_send,
        monitor_socket_path,
        write_runtime_map,
        write_self_awareness_text,
    )

TASK_LINE_RE = re.compile(
    r"^\s*(?:\[(?P<pri>HIGH|MEDIUM|LOW)\]\s+)?(?P<id>TASK-\d+)\s+-\s+(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
PRI_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "": 3}


@dataclass
class BacklogTask:
    id: str
    title: str
    status: str
    priority: str = ""


def tasks_runtime_dir(cfg: SwarmConfig) -> Path:
    return cfg.runtime_dir / "tasks"


def pid_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "dispatcher.pid"


def log_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "dispatcher.log"


def state_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "state.json"


def spec_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "spec.json"


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        return Path(f"/proc/{pid}").exists()


def load_state(cfg: SwarmConfig) -> dict:
    path = state_path(cfg)
    if not path.exists():
        return {"assignments": {}, "history": []}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return {"assignments": {}, "history": []}


def save_state(cfg: SwarmConfig, state: dict) -> None:
    tasks_runtime_dir(cfg).mkdir(parents=True, exist_ok=True)
    state_path(cfg).write_text(json.dumps(state, indent=2) + "\n")


def claim_assignee(cfg: SwarmConfig, pane: str) -> str:
    prefix = (cfg.tasks.claim_assignee_prefix if cfg.tasks else "aiswarm") or "aiswarm"
    return f"{prefix}:{cfg.session_name}:{pane}"


def project_root_for_backlog(tasks: TasksSpec) -> Path:
    if not tasks.backlog_dir:
        raise ValueError("tasks.backlog_dir is not set")
    return tasks.backlog_dir.parent


def _run_backlog(
    tasks: TasksSpec, args: list[str], timeout: float = 30.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["backlog", *args],
        cwd=str(project_root_for_backlog(tasks)),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def parse_task_list_plain(text: str, default_status: str = "") -> list[BacklogTask]:
    """Parse `backlog task list --plain` output into tasks."""
    status = default_status
    out: list[BacklogTask] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith("["):
            # Status headers like "To Do:" / "In Progress:"
            status = stripped[:-1].strip()
            continue
        m = TASK_LINE_RE.match(line)
        if not m:
            continue
        out.append(
            BacklogTask(
                id=m.group("id").upper().replace("TASK", "TASK"),
                title=m.group("title").strip(),
                status=status,
                priority=(m.group("pri") or "").upper(),
            )
        )
    # Normalize TASK- id casing
    for t in out:
        tid = t.id
        if tid.lower().startswith("task-"):
            t.id = "TASK-" + tid.split("-", 1)[1]
    out.sort(key=lambda t: (PRI_RANK.get(t.priority, 3), t.id))
    return out


def list_candidate_tasks(cfg: SwarmConfig) -> list[BacklogTask]:
    tasks = cfg.tasks
    if not tasks:
        return []
    found: list[BacklogTask] = []
    seen: set[str] = set()
    for status in tasks.ingest:
        args = ["task", "list", "-s", status, "--plain", "--limit", "200"]
        if tasks.unassigned_only:
            args.append("--unassigned")
        if tasks.require_label:
            args.extend(["-l", tasks.require_label])
        proc = _run_backlog(tasks, args)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "backlog list failed").strip()
            raise RuntimeError(f"backlog task list failed for status={status!r}: {err}")
        for t in parse_task_list_plain(proc.stdout, default_status=status):
            if t.id not in seen:
                seen.add(t.id)
                found.append(t)
    found.sort(key=lambda t: (PRI_RANK.get(t.priority, 3), t.id))
    return found


def view_task_plain(cfg: SwarmConfig, task_id: str) -> str:
    tasks = cfg.tasks
    if not tasks:
        raise ValueError("no tasks config")
    proc = _run_backlog(tasks, ["task", task_id, "--plain"])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "view failed").strip()
        raise RuntimeError(f"backlog task {task_id} failed: {err}")
    return proc.stdout.strip()


def claim_task(cfg: SwarmConfig, task_id: str, pane: str, dry_run: bool = False) -> str:
    """Claim task via backlog CLI. Returns assignee string used."""
    tasks = cfg.tasks
    if not tasks:
        raise ValueError("no tasks config")
    assignee = claim_assignee(cfg, pane)
    note = f"Claimed by aiswarm tasks dispatcher for pane {pane} (session {cfg.session_name})."
    if dry_run:
        return assignee
    proc = _run_backlog(
        tasks,
        [
            "task",
            "edit",
            task_id,
            "-s",
            "In Progress",
            "-a",
            assignee,
            "--append-notes",
            note,
            "--plain",
        ],
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "edit failed").strip()
        raise RuntimeError(f"claim {task_id} failed: {err}")
    return assignee


def build_task_prompt(cfg: SwarmConfig, task: BacklogTask, pane: str, body: str) -> str:
    assignee = claim_assignee(cfg, pane)
    return (
        f"You have been assigned backlog task {task.id} via aiswarm tasks dispatch.\n"
        f"Session: {cfg.session_name}  Pane: {pane}  Assignee claim: {assignee}\n"
        f"Title: {task.title}\n"
        "\n"
        "Instructions:\n"
        f"1. Read the full task with: backlog task {task.id} --plain\n"
        "2. Implement the work; update the task with notes / AC checks via the backlog CLI.\n"
        f"3. When done, mark complete: backlog task complete {task.id}  (or set status Done).\n"
        "4. Do not wait for further babysit/continue nudges for this assignment — the task is the work unit.\n"
        "5. Prefer durable aiswarm log messaging if you need help from other panes.\n"
        "\n"
        "--- task snapshot ---\n"
        f"{body}\n"
        "--- end snapshot ---\n"
    )


def query_monitor_state(session_name: str, pane: str) -> str:
    sock = monitor_socket_path(session_name, pane)
    if not sock.exists():
        return "unknown"
    try:
        import socket as _socket

        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(str(sock))
            s.sendall(b"status")
            chunks: list[bytes] = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        data = json.loads(b"".join(chunks) or b"{}")
        return str(data.get("state") or data.get("status") or "unknown").lower()
    except Exception:
        return "unknown"


def pane_has_pending(cfg: SwarmConfig, pane: str) -> bool:
    try:
        return bool(get_pending_events(cfg.session_name, pane))
    except Exception:
        return False


def is_pane_free(cfg: SwarmConfig, pane: str, state: dict) -> bool:
    """Free = no local assignment, no pending log events, and idle if required."""
    assignments = state.get("assignments") or {}
    if pane in assignments:
        return False
    if pane_has_pending(cfg, pane):
        return False
    if cfg.tasks and cfg.tasks.require_idle:
        mon = query_monitor_state(cfg.session_name, pane)
        # idle: ok. unknown (no socket / probe fail): allow so once/dry-run works offline.
        # working/rate_limited/etc: not free.
        if mon not in ("idle", "unknown"):
            return False
    return True


def free_task_panes(cfg: SwarmConfig, state: dict) -> list[str]:
    free: list[str] = []
    for p in cfg.task_panes:
        if is_pane_free(cfg, p.pane, state):
            free.append(p.pane)
    return free


def reconcile_assignments(cfg: SwarmConfig, state: dict) -> dict:
    """Drop assignments whose backlog tasks are Done / missing."""
    tasks = cfg.tasks
    if not tasks:
        return state
    assignments = dict(state.get("assignments") or {})
    changed = False
    for pane, info in list(assignments.items()):
        tid = (info or {}).get("task_id")
        if not tid:
            del assignments[pane]
            changed = True
            continue
        proc = _run_backlog(tasks, ["task", tid, "--plain"])
        if proc.returncode != 0:
            continue
        text = proc.stdout.lower()
        if "status:" in text and "done" in text.split("status:", 1)[1].splitlines()[0]:
            history = list(state.get("history") or [])
            history.append(
                {
                    "task_id": tid,
                    "pane": pane,
                    "cleared_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "reason": "done",
                }
            )
            state["history"] = history[-50:]
            del assignments[pane]
            changed = True
    if changed:
        state["assignments"] = assignments
        save_state(cfg, state)
    return state


def desired_spec(cfg: SwarmConfig) -> dict:
    t = cfg.tasks
    return {
        "session": cfg.session_name,
        "config": str(cfg.path),
        "source": t.source if t else None,
        "backlog_dir": str(t.backlog_dir) if t and t.backlog_dir else None,
        "ingest": list(t.ingest) if t else [],
        "poll_secs": t.poll_secs if t else 60,
        "require_label": t.require_label if t else None,
        "unassigned_only": t.unassigned_only if t else True,
        "claim_assignee_prefix": t.claim_assignee_prefix if t else "aiswarm",
        "via_log": t.via_log if t else True,
        "max_inflight": t.max_inflight if t else 0,
        "require_idle": t.require_idle if t else True,
        "panes": [p.pane for p in cfg.task_panes],
    }


def validate_tasks_config(cfg: SwarmConfig) -> None:
    if not cfg.task_panes:
        raise ValueError(
            "no panes with nudge.tasks.enabled: true; enable at least one pane for tasks dispatch"
        )
    if not cfg.tasks:
        raise ValueError("tasks config missing (set top-level tasks: or enable pane tasks near a backlog/)")
    if cfg.tasks.source != "backlog":
        raise ValueError(f"unsupported tasks.source: {cfg.tasks.source}")
    for p in cfg.task_panes:
        if p.babysit.enabled:
            print(
                f"warning: pane {p.pane} has both babysit.enabled and tasks.enabled; "
                "prefer only tasks for that pane to avoid prompt fights",
                file=sys.stderr,
            )


def dispatch_once(cfg: SwarmConfig, dry_run: bool = False) -> list[dict]:
    """Claim+dispatch at most one task per free pane. Returns list of actions taken."""
    validate_tasks_config(cfg)
    assert cfg.tasks is not None
    state = reconcile_assignments(cfg, load_state(cfg))
    free = free_task_panes(cfg, state)
    if not free:
        return []
    candidates = list_candidate_tasks(cfg)
    # Skip tasks already assigned in local state
    assigned_ids = {
        (info or {}).get("task_id")
        for info in (state.get("assignments") or {}).values()
    }
    candidates = [t for t in candidates if t.id not in assigned_ids]
    actions: list[dict] = []
    max_n = cfg.tasks.max_inflight
    inflight = len(state.get("assignments") or {})
    for pane in free:
        if max_n and inflight >= max_n:
            break
        if not candidates:
            break
        task = candidates.pop(0)
        body = ""
        if not dry_run:
            try:
                body = view_task_plain(cfg, task.id)
            except Exception as e:
                body = f"(could not load task body: {e})"
        else:
            body = f"(dry-run snapshot for {task.id})"
        prompt = build_task_prompt(cfg, task, pane, body)
        assignee = claim_task(cfg, task.id, pane, dry_run=dry_run)
        event_id = None
        if dry_run:
            print(
                f"would claim {task.id} -> pane {pane} assignee={assignee} "
                f"and deliver via {'log' if cfg.tasks.via_log else 'direct'}"
            )
        else:
            if cfg.tasks.via_log:
                event_id = log_send(
                    cfg.session_name,
                    pane,
                    prompt,
                    sender="tasks-dispatch",
                    etype="task",
                    meta={"task_id": task.id, "pane": pane, "assignee": assignee},
                )
            else:
                # Direct fallback via tmux-send
                target = f"{cfg.session_name}:{pane}"
                subprocess.run(
                    [str(ROOT_DIR / "tmux-send"), "--no-prefix", target, prompt],
                    check=False,
                )
            assignments = dict(state.get("assignments") or {})
            assignments[pane] = {
                "task_id": task.id,
                "title": task.title,
                "assignee": assignee,
                "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event_id": event_id,
            }
            state["assignments"] = assignments
            state["last_dispatch"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_state(cfg, state)
            inflight = len(assignments)
            print(f"dispatched {task.id} -> {cfg.session_name}:{pane} event_id={event_id}")
        actions.append(
            {
                "task_id": task.id,
                "pane": pane,
                "assignee": assignee,
                "event_id": event_id,
                "dry_run": dry_run,
            }
        )
    return actions


def start_dispatcher(cfg: SwarmConfig, dry_run: bool = False) -> None:
    validate_tasks_config(cfg)
    tasks_runtime_dir(cfg).mkdir(parents=True, exist_ok=True)
    wanted = desired_spec(cfg)
    path = pid_path(cfg)
    if path.exists():
        pid = int(path.read_text().strip() or "0")
        if process_running(pid):
            cur = {}
            if spec_path(cfg).exists():
                try:
                    cur = json.loads(spec_path(cfg).read_text() or "{}")
                except json.JSONDecodeError:
                    cur = {}
            if cur == wanted:
                print(f"tasks dispatcher already running for {cfg.session_name} pid={pid}")
                return
            if dry_run:
                print(f"would restart tasks dispatcher for {cfg.session_name} pid={pid}")
            else:
                stop_dispatcher(cfg, dry_run=False)
    if dry_run:
        print(
            f"would start tasks dispatcher session={cfg.session_name} "
            f"panes={[p.pane for p in cfg.task_panes]} "
            f"backlog_dir={cfg.tasks.backlog_dir if cfg.tasks else None} "
            f"ingest={cfg.tasks.ingest if cfg.tasks else None}"
        )
        spec_path(cfg).write_text(json.dumps(wanted, indent=2) + "\n")
        write_runtime_map(cfg)
        write_self_awareness_text(cfg)
        return
    env = dict(os.environ)
    env["AISWARM_TASKS_CONFIG"] = str(cfg.path)
    with log_path(cfg).open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "tasks_dispatch.py"), str(cfg.path)],
            stdout=log,
            stderr=log,
            start_new_session=True,
            text=True,
            env=env,
        )
    pid_path(cfg).write_text(str(proc.pid) + "\n")
    spec_path(cfg).write_text(json.dumps(wanted, indent=2) + "\n")
    write_runtime_map(cfg)
    write_self_awareness_text(cfg)
    print(f"Started tasks dispatcher for {cfg.session_name} pid={proc.pid}")


def stop_dispatcher(cfg: SwarmConfig, dry_run: bool = False) -> None:
    path = pid_path(cfg)
    if not path.exists():
        print(f"No tasks dispatcher pid for {cfg.session_name}")
        return
    pid = int(path.read_text().strip() or "0")
    if dry_run:
        print(f"would stop tasks dispatcher session={cfg.session_name} pid={pid}")
        return
    if pid and process_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        # brief wait
        for _ in range(20):
            if not process_running(pid):
                break
            time.sleep(0.05)
        if process_running(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    path.unlink(missing_ok=True)
    print(f"Stopped tasks dispatcher for {cfg.session_name}")


def status(cfg: SwarmConfig) -> None:
    t = cfg.tasks
    print(f"session: {cfg.session_name}")
    print(f"config:  {cfg.path}")
    if not t:
        print("tasks:   (no session tasks config)")
    else:
        print(f"source:  {t.source}")
        print(f"backlog: {t.backlog_dir}")
        print(f"ingest:  {t.ingest}")
        print(f"poll:    {t.poll_secs}s  unassigned_only={t.unassigned_only} "
              f"require_label={t.require_label!r} require_idle={t.require_idle}")
    panes = cfg.task_panes
    print(f"task panes ({len(panes)}): " + (
        ", ".join(f"{p.pane}({p.title})" for p in panes) if panes else "(none)"
    ))
    path = pid_path(cfg)
    if path.exists():
        pid = int(path.read_text().strip() or "0")
        alive = process_running(pid) if pid else False
        print(f"dispatcher: pid={pid} {'running' if alive else 'dead'}")
    else:
        print("dispatcher: not started")
    state = load_state(cfg)
    assignments = state.get("assignments") or {}
    if assignments:
        print("assignments:")
        for pane, info in sorted(assignments.items()):
            print(
                f"  {pane}: {info.get('task_id')} "
                f"assignee={info.get('assignee')} claimed_at={info.get('claimed_at')}"
            )
    else:
        print("assignments: (none)")
    # candidates preview
    if t and panes:
        try:
            cands = list_candidate_tasks(cfg)
            print(f"candidates ({len(cands)}):")
            for c in cands[:15]:
                pri = f"[{c.priority}] " if c.priority else ""
                print(f"  {pri}{c.id} - {c.title} ({c.status})")
            if len(cands) > 15:
                print(f"  ... +{len(cands) - 15} more")
        except Exception as e:
            print(f"candidates: error: {e}")
