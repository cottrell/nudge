#!/usr/bin/env python3
"""Control plane for the session-level tasks dispatcher (not babysit).

Backlog source adapter uses structured CLI JSON only:
  backlog task list … --json
  backlog task <id> --json

Requires Backlog.md with BACK-545 (main / post-1.48.0 release). Do not scrape --plain.
"""
from __future__ import annotations

import json
import os
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
        effective_config_dict,
        get_pending_events,
        log_send,
        monitor_socket_path,
        resolve_backlog_dir,
        write_runtime_map,
    )
except ImportError:
    from common import (
        ROOT_DIR,
        SwarmConfig,
        TasksSpec,
        effective_config_dict,
        get_pending_events,
        log_send,
        monitor_socket_path,
        resolve_backlog_dir,
        write_runtime_map,
    )

# Priority order for dispatch (matches backlog high/medium/low).
PRI_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "": 3}

# Expected envelope from backlog --json (schemaVersion may bump; we only require kind/tasks).
BACKLOG_JSON_NOTE = (
    "aiswarm tasks requires backlog CLI --json (Backlog.md BACK-545; main / next release after 1.48.0). "
    "Install from git until published: see Backlog.md Makefile install-dev."
)


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
    return f"{cfg.tasks.claim_assignee_prefix}:{cfg.session_name}:{pane}"


def ensure_backlog_dir(cfg: SwarmConfig) -> Path:
    """Backlog source adapter: explicit tasks.backlog_dir or walk-up. Fails if absent."""
    t = cfg.tasks
    if t.source != "backlog":
        raise ValueError(f"ensure_backlog_dir only for source=backlog, got {t.source!r}")
    if t.backlog_dir is not None:
        return t.backlog_dir
    found = resolve_backlog_dir(cfg.path, None)
    t.backlog_dir = found  # cache on filled config
    return found


def project_root_for_backlog(cfg: SwarmConfig) -> Path:
    return ensure_backlog_dir(cfg).parent


def _run_backlog(
    cfg: SwarmConfig, args: list[str], timeout: float = 30.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["backlog", *args],
        cwd=str(project_root_for_backlog(cfg)),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def _json_or_raise(proc: subprocess.CompletedProcess[str], what: str) -> dict:
    """Parse backlog --json stdout. Clear error if CLI lacks --json."""
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    combined = f"{out}\n{err}".lower()
    if "unknown option" in combined and "json" in combined:
        raise RuntimeError(f"{what}: {BACKLOG_JSON_NOTE} stderr={err or out}")
    if proc.returncode != 0 and not out:
        raise RuntimeError(f"{what}: {(err or out or 'backlog failed').strip()}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"{what}: expected JSON ({BACKLOG_JSON_NOTE}); parse error: {e}; "
            f"stdout[:200]={out[:200]!r}"
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError(f"{what}: JSON root must be object, got {type(data).__name__}")
    return data


def parse_task_list_json(data: dict) -> list[BacklogTask]:
    """Parse `backlog task list --json` envelope into BacklogTask list."""
    tasks_raw = data.get("tasks")
    if tasks_raw is None:
        raise ValueError(f"task-list JSON missing 'tasks' (kind={data.get('kind')!r})")
    out: list[BacklogTask] = []
    for row in tasks_raw:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("id") or "").strip()
        if not tid:
            continue
        pri = str(row.get("priority") or "").strip().upper()
        out.append(
            BacklogTask(
                id=tid,
                title=str(row.get("title") or "").strip(),
                status=str(row.get("status") or "").strip(),
                priority=pri,
            )
        )
    out.sort(key=lambda t: (PRI_RANK.get(t.priority, 3), t.id))
    return out


def list_candidate_tasks(cfg: SwarmConfig) -> list[BacklogTask]:
    tasks = cfg.tasks
    found: list[BacklogTask] = []
    seen: set[str] = set()
    for status in tasks.ingest:
        args = ["task", "list", "-s", status, "--json", "--limit", "200"]
        if tasks.unassigned_only:
            args.append("--unassigned")
        if tasks.require_label:
            args.extend(["-l", tasks.require_label])
        proc = _run_backlog(cfg, args)
        data = _json_or_raise(proc, f"backlog task list status={status!r}")
        for t in parse_task_list_json(data):
            if t.id not in seen:
                seen.add(t.id)
                found.append(t)
    found.sort(key=lambda t: (PRI_RANK.get(t.priority, 3), t.id))
    return found


def view_task_json(cfg: SwarmConfig, task_id: str) -> dict:
    """Return task object from `backlog task <id> --json`."""
    proc = _run_backlog(cfg, ["task", task_id, "--json"])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "view failed").strip()
        raise RuntimeError(f"backlog task {task_id}: {err}")
    data = _json_or_raise(proc, f"backlog task {task_id} --json")
    task = data.get("task")
    if not isinstance(task, dict):
        raise RuntimeError(f"backlog task {task_id}: JSON missing 'task' object")
    return task


def format_task_snapshot(task: dict) -> str:
    """Human-readable snapshot for the agent prompt (from JSON task object)."""
    lines = [
        f"id: {task.get('id')}",
        f"title: {task.get('title')}",
        f"status: {task.get('status')}",
        f"priority: {task.get('priority')}",
        f"type: {task.get('type')}",
        f"assignees: {task.get('assignees')}",
        f"labels: {task.get('labels')}",
    ]
    if task.get("description"):
        lines.extend(["", "## description", str(task["description"])])
    ac = task.get("acceptanceCriteria") or []
    if ac:
        lines.extend(["", "## acceptance criteria"])
        for item in ac:
            mark = "x" if item.get("checked") else " "
            lines.append(f"- [{mark}] {item.get('text', '')}")
    if task.get("implementationPlan"):
        lines.extend(["", "## plan", str(task["implementationPlan"])])
    if task.get("implementationNotes"):
        lines.extend(["", "## notes", str(task["implementationNotes"])])
    return "\n".join(lines).strip()


def view_task_plain(cfg: SwarmConfig, task_id: str) -> str:
    """Snapshot text for dispatch prompt (backed by --json, not --plain scrape)."""
    return format_task_snapshot(view_task_json(cfg, task_id))


def claim_task(cfg: SwarmConfig, task_id: str, pane: str, dry_run: bool = False) -> str:
    """Claim task via backlog CLI. Returns assignee string used."""
    assignee = claim_assignee(cfg, pane)
    note = f"Claimed by aiswarm tasks dispatcher for pane {pane} (session {cfg.session_name})."
    if dry_run:
        return assignee
    proc = _run_backlog(
        cfg,
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
    if cfg.tasks.require_idle:
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
    assignments = dict(state.get("assignments") or {})
    changed = False
    for pane, info in list(assignments.items()):
        tid = (info or {}).get("task_id")
        if not tid:
            del assignments[pane]
            changed = True
            continue
        proc = _run_backlog(cfg, ["task", tid, "--json"])
        text = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
        is_done = False
        reason = "done"
        if proc.returncode != 0 and "not found" in text:
            is_done = True
            reason = "not_found"
        elif proc.returncode == 0:
            try:
                data = json.loads((proc.stdout or "").strip() or "{}")
                st = str((data.get("task") or {}).get("status") or "").strip().lower()
                if st == "done":
                    is_done = True
            except json.JSONDecodeError:
                pass
        if is_done:
            history = list(state.get("history") or [])
            history.append(
                {
                    "task_id": tid,
                    "pane": pane,
                    "cleared_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "reason": reason,
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
    """Runtime dispatcher fingerprint from already-filled cfg (no defaults)."""
    t = cfg.tasks
    return {
        "session": cfg.session_name,
        "config": str(cfg.path),
        "source": t.source,
        "backlog_dir": str(t.backlog_dir) if t.backlog_dir else None,
        "ingest": list(t.ingest),
        "poll_secs": t.poll_secs,
        "require_label": t.require_label,
        "unassigned_only": t.unassigned_only,
        "claim_assignee_prefix": t.claim_assignee_prefix,
        "via_log": t.via_log,
        "max_inflight": t.max_inflight,
        "require_idle": t.require_idle,
        "panes": [p.pane for p in cfg.task_panes],
    }


def validate_tasks_config(cfg: SwarmConfig) -> None:
    if not cfg.task_panes:
        raise ValueError(
            "no task-enabled panes (monitored panes default on; "
            "opt out with nudge.tasks.enabled: false)"
        )
    if cfg.tasks.source != "backlog":
        raise ValueError(f"unsupported tasks.source: {cfg.tasks.source}")
    # Source adapter detail: resolve/discover only when actually running tasks.
    ensure_backlog_dir(cfg)
    for p in cfg.task_panes:
        if p.babysit.enabled:
            print(
                f"warning: pane {p.pane} has both babysit.enabled and tasks.enabled; "
                "prefer only tasks for that pane to avoid prompt fights",
                file=sys.stderr,
            )


def print_effective_tasks(cfg: SwarmConfig) -> None:
    """Print resolved tasks defaults (used by dry-run)."""
    eff = effective_config_dict(cfg)
    print("effective config (defaults filled):")
    print(yaml_dump_tasks(eff))


def yaml_dump_tasks(eff: dict) -> str:
    try:
        import yaml

        return yaml.safe_dump(eff, default_flow_style=False, sort_keys=False).rstrip()
    except Exception:
        return json.dumps(eff, indent=2)


def dispatch_once(cfg: SwarmConfig, dry_run: bool = False) -> list[dict]:
    """Claim+dispatch at most one task per free pane. Returns list of actions taken."""
    validate_tasks_config(cfg)
    assert cfg.tasks is not None
    if dry_run:
        print_effective_tasks(cfg)
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
            f"backlog_dir={cfg.tasks.backlog_dir} "
            f"ingest={cfg.tasks.ingest}"
        )
        print_effective_tasks(cfg)
        spec_path(cfg).write_text(json.dumps(wanted, indent=2) + "\n")
        write_runtime_map(cfg)
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
