#!/usr/bin/env python3
"""Control plane for the session-level tasks dispatcher (not babysit).

Each pass:
  1) chase: assigned + pane idle → re-prompt until Done / unassigned / gone
  2) claim: free panes get new unassigned ingest tasks (default To Do)

Backlog JSON only (BACK-545). unassigned_only filters *new* claims, not chase.
"""
from __future__ import annotations

import json
import os
import secrets
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    from .common import (
        ROOT_DIR,
        SwarmConfig,
        TasksSpec,
        effective_config_dict,
        get_pending_events,
        get_events,
        log_send,
        resolve_backlog_dir,
        query_monitor_state as shared_query_monitor_state,
        write_runtime_map,
        monitor_socket_path,
    )
except ImportError:
    from common import (
        ROOT_DIR,
        SwarmConfig,
        TasksSpec,
        effective_config_dict,
        get_pending_events,
        get_events,
        log_send,
        resolve_backlog_dir,
        query_monitor_state as shared_query_monitor_state,
        write_runtime_map,
        monitor_socket_path,
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
    assignees: list[str] = None

    def __post_init__(self) -> None:
        if self.assignees is None:
            self.assignees = []


@dataclass
class DependencyGate:
    ready: bool
    blocked: bool
    reason: str = ""
    blocked_on: list[str] = None
    missing: list[str] = None
    cycle: list[str] = None

    def __post_init__(self) -> None:
        if self.blocked_on is None:
            self.blocked_on = []
        if self.missing is None:
            self.missing = []
        if self.cycle is None:
            self.cycle = []


def tasks_runtime_dir(cfg: SwarmConfig) -> Path:
    return cfg.runtime_dir / "tasks"


def pid_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "dispatcher.pid"


def log_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "dispatcher.log"


def state_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "state.json"


def worker_state_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "worker_state.json"


def spec_path(cfg: SwarmConfig) -> Path:
    return tasks_runtime_dir(cfg) / "spec.json"


def enabled_path(cfg: SwarmConfig) -> Path:
    """Flag consumed by the session worker; tasks is a loop group, not a process."""
    return tasks_runtime_dir(cfg) / "enabled.json"


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_pid(path: Path) -> int:
    try:
        return int(path.read_text().strip() or "0")
    except (OSError, ValueError):
        return 0
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
    """Atomic write (temp file + rename) so a crash mid-write can't truncate state.json."""
    tasks_runtime_dir(cfg).mkdir(parents=True, exist_ok=True)
    path = state_path(cfg)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    os.replace(tmp, path)


def save_worker_state(cfg: SwarmConfig, next_poll_at: float) -> None:
    tasks_runtime_dir(cfg).mkdir(parents=True, exist_ok=True)
    path = worker_state_path(cfg)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps({"next_poll_at": next_poll_at}) + "\n")
    os.replace(tmp, path)


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
                assignees=_task_assignees(row),
            )
        )
    out.sort(key=lambda t: (PRI_RANK.get(t.priority, 3), t.id))
    return out


def list_candidate_tasks(
    cfg: SwarmConfig, *, unassigned_only: bool | None = None
) -> list[BacklogTask]:
    tasks = cfg.tasks
    unassigned_only = tasks.unassigned_only if unassigned_only is None else unassigned_only
    found: list[BacklogTask] = []
    seen: set[str] = set()
    for status in tasks.ingest:
        args = ["task", "list", "-s", status, "--json", "--limit", "200"]
        if unassigned_only:
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


def view_completed_task(cfg: SwarmConfig, task_id: str) -> dict | None:
    """Read a task moved out of Backlog's editable JSON view by task complete."""
    completed = ensure_backlog_dir(cfg) / "completed"
    if not completed.is_dir():
        return None
    for path in completed.glob("*.md"):
        text = path.read_text()
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---", 4)
        if end < 0:
            continue
        data = yaml.safe_load(text[4:end]) or {}
        if isinstance(data, dict) and str(data.get("id") or "").strip() == task_id:
            return data
    return None


def _complete_statuses(cfg: SwarmConfig) -> set[str]:
    """Lowercased complete statuses from TasksSpec (always filled by load_config)."""
    return {
        str(status).strip().lower()
        for status in (cfg.tasks.complete_statuses or [])
        if str(status).strip()
    } or {"done"}


def _task_status(task: dict) -> str:
    return str(task.get("status") or "").strip().lower()


def task_is_complete(cfg: SwarmConfig, task: dict) -> bool:
    """True when task status is in tasks.complete_statuses (case-insensitive).

    Shared by dependency_gate and view_assignment so both use one predicate.
    Works for active tasks and for dicts loaded via view_completed_task.
    """
    return _task_status(task) in _complete_statuses(cfg)


def _task_assignees(task: dict) -> list[str]:
    raw = task.get("assignees")
    if raw is None:
        raw = task.get("assignee")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        s = str(item or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _skip_assignee_set(cfg: SwarmConfig) -> set[str]:
    return {a.strip().lower() for a in (cfg.tasks.skip_assignees or []) if str(a).strip()}


def is_swarm_assignee(cfg: SwarmConfig, assignee: str) -> bool:
    """True for aiswarm:<session>:<pane> (or bare prefix)."""
    a = (assignee or "").strip().lower()
    if not a:
        return False
    prefix = (cfg.tasks.claim_assignee_prefix or "aiswarm").strip().lower()
    return a == prefix or a.startswith(f"{prefix}:")


def is_skip_assignee(cfg: SwarmConfig, assignee: str) -> bool:
    """True if assignee is in tasks.skip_assignees (dispatcher leaves alone)."""
    return (assignee or "").strip().lower() in _skip_assignee_set(cfg)


def task_skipped_for_claim(cfg: SwarmConfig, task: dict | BacklogTask) -> bool:
    """True if this task should not enter the claim pool (skip_assignees hands-off).

    Swarm aiswarm: owners are not 'skipped' for claim (they're already owned).
    Non-swarm assignees in skip_assignees → do not claim/reclaim.
    """
    if isinstance(task, BacklogTask):
        # list rows may not carry assignees; treat as not skip-filtered here
        return False
    assignees = _task_assignees(task)
    if not assignees:
        return False
    if any(is_swarm_assignee(cfg, a) for a in assignees):
        return False
    return any(is_skip_assignee(cfg, a) for a in assignees)


def _dependency_ids(task: dict) -> list[str]:
    raw = task.get("dependencies")
    if raw is None:
        raw = task.get("dependencyIds") or task.get("dependsOn") or []
    if isinstance(raw, str):
        raw = [raw]
    ids: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            dep_id = (
                item.get("id")
                or item.get("taskId")
                or item.get("task_id")
                or item.get("dependencyId")
            )
        else:
            dep_id = item
        dep = str(dep_id or "").strip()
        if dep and dep not in ids:
            ids.append(dep)
    return ids


def _task_or_none(cfg: SwarmConfig, task_id: str, cache: dict[str, dict | None]) -> dict | None:
    if task_id in cache:
        return cache[task_id]
    try:
        task = view_task_json(cfg, task_id)
    except RuntimeError as e:
        if "not found" in str(e).lower():
            task = view_completed_task(cfg, task_id)
            cache[task_id] = task
            return task
        raise
    cache[task_id] = task
    return task


def _dependency_graph_issue(
    cfg: SwarmConfig,
    task_id: str,
    cache: dict[str, dict | None],
    stack: list[str],
) -> DependencyGate:
    if task_id in stack:
        cycle = stack[stack.index(task_id):] + [task_id]
        return DependencyGate(False, True, reason="cycle", cycle=cycle)
    task = _task_or_none(cfg, task_id, cache)
    if task is None:
        return DependencyGate(False, True, reason="missing", missing=[task_id])
    deps = _dependency_ids(task)
    if task_id in deps:
        return DependencyGate(False, True, reason="self-dependency", blocked_on=[task_id], cycle=[task_id, task_id])
    next_stack = stack + [task_id]
    for dep_id in deps:
        issue = _dependency_graph_issue(cfg, dep_id, cache, next_stack)
        if issue.blocked:
            return issue
    return DependencyGate(True, False)


def dependency_gate(
    cfg: SwarmConfig,
    task_id: str,
    *,
    cache: dict[str, dict | None] | None = None,
) -> DependencyGate:
    cache = cache if cache is not None else {}
    task = _task_or_none(cfg, task_id, cache)
    if task is None:
        return DependencyGate(False, True, reason="missing", missing=[task_id])

    graph_issue = _dependency_graph_issue(cfg, task_id, cache, [])
    if graph_issue.blocked:
        return graph_issue

    deps = _dependency_ids(task)
    if not deps:
        return DependencyGate(True, False)

    # Deps are status-only: incomplete (any assignee, including human) blocks the parent.
    blocked_on: list[str] = []
    missing: list[str] = []
    for dep_id in deps:
        dep = _task_or_none(cfg, dep_id, cache)
        if dep is None:
            missing.append(dep_id)
            continue
        if not task_is_complete(cfg, dep):
            blocked_on.append(dep_id)

    if missing:
        return DependencyGate(
            False, True, reason="missing", blocked_on=blocked_on, missing=missing
        )
    if blocked_on:
        return DependencyGate(False, True, reason="waiting", blocked_on=blocked_on)
    return DependencyGate(True, False)


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


def build_task_prompt(
    cfg: SwarmConfig, task: BacklogTask, pane: str, body: str, *, chase: bool = False
) -> str:
    assignee = claim_assignee(cfg, pane)
    if chase:
        # Short: avoid re-spamming full snapshot every throttle window (and vs babysit).
        return (
            f"Reminder: backlog task {task.id} is still assigned to you "
            f"(pane {pane}). Keep going or Done. Blocked/deferred? Unassign with: "
            f"backlog task edit {task.id} -a ''\n"
            f"Title: {task.title}\n"
            f"Re-read if needed: backlog task {task.id} --plain\n"
        )
    return (
        f"You have been assigned backlog task {task.id} via aiswarm tasks dispatch.\n"
        f"Session: {cfg.session_name}  Pane: {pane}  Assignee claim: {assignee}\n"
        f"Title: {task.title}\n"
        "\n"
        "Instructions:\n"
        f"1. Read the full task with: backlog task {task.id} --plain\n"
        "2. Implement the work; update the task with notes / AC checks via the backlog CLI.\n"
        f"3. When done: backlog task complete {task.id} (or status Done).\n"
        "4. If you cannot do this now (blocked, wrong priority, or deferred):\n"
        "   - If blocked on other work, depend on it: "
        f"`backlog task edit {task.id} --depends-on <blocker-task-id>` "
        "(parent is not claimable/chaseable until every dep is Done).\n"
        "   - To leave it for a human (dispatcher will skip claim): "
        f"`backlog task edit {task.id} -a human` "
        "(names in tasks.skip_assignees; default includes human).\n"
        "   - Never use model names as assignees; use aiswarm:<session>:<pane> or clear assignee.\n"
        f"   - Or unassign: backlog task edit {task.id} -a '' and optionally -s 'To Do'\n"
        "5. Prefer durable aiswarm log messaging if you need help from other panes.\n"
        "\n"
        "--- task snapshot ---\n"
        f"{body}\n"
        "--- end snapshot ---\n"
    )


def _blocked_signature(gate: DependencyGate) -> dict:
    return {
        "reason": gate.reason,
        "blocked_on": list(gate.blocked_on),
        "missing": list(gate.missing),
        "cycle": list(gate.cycle),
    }


def _blocked_prompt(gate: DependencyGate) -> str:
    parts: list[str] = []
    if gate.reason == "cycle":
        parts.append(f"dependency cycle: {' -> '.join(gate.cycle)}")
    elif gate.reason == "missing":
        if gate.missing:
            parts.append(f"missing dependency ids: {', '.join(gate.missing)}")
        if gate.blocked_on:
            parts.append(f"waiting on: {', '.join(gate.blocked_on)}")
    else:
        if gate.blocked_on:
            parts.append(f"waiting on: {', '.join(gate.blocked_on)}")
        if gate.missing:
            parts.append(f"missing dependency ids: {', '.join(gate.missing)}")
    return "; ".join(parts) or gate.reason or "blocked"


def _parse_assignment_ts(raw: str | None) -> float | None:
    """Parse state timestamps (claimed_at / last_chased_at / recovered_at) → epoch seconds."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return time.mktime(time.strptime(s[:19], fmt))
        except ValueError:
            continue
    return None


def chase_due(info: dict | None, min_chase_secs: int, now: float | None = None) -> bool:
    """True if this assignment may be chased (min interval elapsed or no prior stamp)."""
    if min_chase_secs <= 0:
        return True
    now = time.time() if now is None else now
    info = info or {}
    last = (
        _parse_assignment_ts(info.get("last_chased_at"))
        or _parse_assignment_ts(info.get("claimed_at"))
        or _parse_assignment_ts(info.get("recovered_at"))
    )
    if last is None:
        return True
    return (now - last) >= min_chase_secs


def healthcheck_recipient(pane: str) -> str:
    return f"{pane}:healthcheck"


def healthcheck_ponged(cfg: SwarmConfig, pane: str, nonce: str) -> bool:
    """Only an explicit agent-pong event counts; consumer delivery acks never do."""
    for _eid, _ts, recipient, sender, etype, payload, _meta in get_events(
        cfg.session_name, healthcheck_recipient(pane)
    ):
        if (
            recipient == healthcheck_recipient(pane)
            and sender == "agent-pong"
            and etype == "healthcheck-pong"
            and nonce in payload
        ):
            return True
    return False


def send_healthcheck(
    cfg: SwarmConfig, pane: str, task_id: str, *, dry_run: bool = False
) -> dict:
    nonce = secrets.token_urlsafe(12)
    payload = (
        f"HEALTHCHECK for assigned task {task_id}. If you can read this, reply now with:\n"
        f"aiswarm healthcheck pong {pane} {nonce}\n"
        "This is a one-off stall check, not a continuous heartbeat."
    )
    if dry_run:
        return {"nonce": nonce, "sent_at": time.time(), "event_id": None, "dry_run": True}
    event_id = log_send(
        cfg.session_name,
        pane,
        payload,
        sender="tasks-dispatch",
        etype="healthcheck",
        meta={"task_id": task_id, "pane": pane, "nonce": nonce},
    )
    return {"nonce": nonce, "sent_at": time.time(), "event_id": event_id}


def pane_respawn_argv(command: str) -> list[str]:
    """Split shell_command into argv for tmux respawn-pane (not one blob string)."""
    argv = shlex.split(command or "")
    if not argv:
        raise ValueError("empty shell_command for pane respawn")
    return argv


def respawn_task_pane(cfg: SwarmConfig, pane: str) -> None:
    """Restart one configured pane and attach a fresh activity monitor."""
    pane_spec = next(p for p in cfg.task_panes if p.pane == pane)
    target = pane_spec.target(cfg.session_name)
    argv = pane_respawn_argv(pane_spec.command)
    subprocess.run(["tmux", "pipe-pane", "-t", target, ""], check=False, text=True)
    monitor_socket_path(cfg.session_name, pane).unlink(missing_ok=True)
    subprocess.run(
        ["tmux", "respawn-pane", "-k", "-t", target, "--", *argv],
        check=True,
        text=True,
    )
    if pane_spec.monitor:
        subprocess.run(
            [str(ROOT_DIR / "attach.sh"), target, pane_spec.agent or "claude"],
            check=True,
            text=True,
        )


def deliver_task_prompt(
    cfg: SwarmConfig, pane: str, prompt: str, *, dry_run: bool, meta: dict | None = None
) -> int | None:
    """Send prompt via log (default) or direct tmux-send. Returns event_id if log."""
    if dry_run:
        return None
    if cfg.tasks.via_log:
        return log_send(
            cfg.session_name,
            pane,
            prompt,
            sender="tasks-dispatch",
            etype="task",
            meta=meta or {},
        )
    target = f"{cfg.session_name}:{pane}"
    subprocess.run(
        [str(ROOT_DIR / "tmux-send"), "--no-prefix", target, prompt],
        check=False,
    )
    return None


def pane_ready_for_prompt(cfg: SwarmConfig, pane: str) -> bool:
    """True if we may inject a tasks prompt (idle + no pending log)."""
    if pane_has_pending(cfg, pane):
        return False
    if cfg.tasks.require_idle:
        mon = query_monitor_state(cfg.session_name, pane)
        if mon != "idle":
            return False
    return True


def query_monitor_state(session_name: str, pane: str) -> str:
    return shared_query_monitor_state(session_name, pane)


def pane_has_pending(cfg: SwarmConfig, pane: str) -> bool:
    try:
        return bool(get_pending_events(cfg.session_name, pane))
    except Exception:
        return False


def is_pane_free(cfg: SwarmConfig, pane: str, state: dict) -> bool:
    """Free for *new* claim: no local assignment + ready for prompt."""
    if pane in (state.get("assignments") or {}):
        return False
    return pane_ready_for_prompt(cfg, pane)


def free_task_panes(cfg: SwarmConfig, state: dict) -> list[str]:
    return [p.pane for p in cfg.task_panes if is_pane_free(cfg, p.pane, state)]


@dataclass
class AssignmentView:
    """Lifecycle of a local pane→task assignment vs backlog (single source of truth)."""

    kind: str  # open | done | missing | unassigned | error | empty
    task: dict | None = None
    reason: str = ""


def view_assignment(
    cfg: SwarmConfig,
    pane: str,
    task_id: str | None,
    *,
    cache: dict[str, dict | None] | None = None,
) -> AssignmentView:
    """How this assignment looks now. Used by reconcile + chase (do not duplicate).

    Shares `cache` with dependency_gate so reconcile + chase reuse one fetch per task
    within a dispatch pass instead of each issuing its own `backlog task <id> --json`.
    """
    if not task_id:
        return AssignmentView("empty", reason="no_task_id")
    cache = cache if cache is not None else {}
    try:
        task = _task_or_none(cfg, task_id, cache)
    except RuntimeError as e:
        return AssignmentView("error", reason=str(e))
    if task is None:
        return AssignmentView("missing", reason="not_found")
    if task_is_complete(cfg, task):
        return AssignmentView("done", task=task, reason="done")
    assignees = task.get("assignees") or []
    if isinstance(assignees, str):
        assignees = [assignees]
    want = claim_assignee(cfg, pane)
    if not assignees or want not in assignees:
        return AssignmentView("unassigned", task=task, reason="assignee_cleared")
    return AssignmentView("open", task=task)


def _clear_assignment(state: dict, pane: str, task_id: str, reason: str) -> None:
    history = list(state.get("history") or [])
    history.append(
        {
            "task_id": task_id,
            "pane": pane,
            "cleared_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "reason": reason,
        }
    )
    state["history"] = history[-50:]
    assignments = dict(state.get("assignments") or {})
    assignments.pop(pane, None)
    state["assignments"] = assignments


def _call_view_assignment(cfg: SwarmConfig, pane: str, task_id: str | None, cache: dict | None) -> AssignmentView:
    import inspect
    try:
        sig = inspect.signature(view_assignment)
        if "cache" in sig.parameters:
            return view_assignment(cfg, pane, task_id, cache=cache)
    except Exception:
        pass
    return view_assignment(cfg, pane, task_id)


def reconcile_assignments(
    cfg: SwarmConfig, state: dict, *, cache: dict[str, dict | None] | None = None
) -> dict:
    """Drop assignments that are done / missing / no longer assigned to this pane."""
    cache = cache if cache is not None else {}
    assignments = dict(state.get("assignments") or {})
    changed = False
    for pane, info in list(assignments.items()):
        tid = (info or {}).get("task_id")
        view = _call_view_assignment(cfg, pane, tid, cache)
        if view.kind in ("done", "missing", "unassigned", "empty"):
            _clear_assignment(state, pane, tid or "", view.reason or view.kind)
            changed = True
    if changed:
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
        "min_chase_secs": t.min_chase_secs,
        "healthcheck_chases": t.healthcheck_chases,
        "healthcheck_timeout_secs": t.healthcheck_timeout_secs,
        "healthcheck_max_restarts": t.healthcheck_max_restarts,
        "skip_assignees": list(t.skip_assignees),
        "complete_statuses": list(t.complete_statuses),
        "panes": [p.pane for p in cfg.task_panes],
    }


_babysit_tasks_warned: set[tuple[str, str]] = set()


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
            key = (cfg.session_name, p.pane)
            if key in _babysit_tasks_warned:
                continue
            _babysit_tasks_warned.add(key)
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


def chase_assigned(
    cfg: SwarmConfig,
    state: dict,
    dry_run: bool = False,
    *,
    cache: dict[str, dict | None] | None = None,
) -> list[dict]:
    """Re-prompt idle panes that still own an open assignment (until Done/unassign/gone).

    Throttled by tasks.min_chase_secs (default = poll_secs: one chase opportunity per pass).
    """
    actions: list[dict] = []
    changed = False
    min_chase = cfg.tasks.min_chase_secs
    now = time.time()
    cache = cache if cache is not None else {}
    for pane, info in list((state.get("assignments") or {}).items()):
        tid = (info or {}).get("task_id")
        view = _call_view_assignment(cfg, pane, tid, cache)
        if view.kind in ("done", "missing", "unassigned", "empty"):
            _clear_assignment(state, pane, tid or "", view.reason or view.kind)
            changed = True
            continue
        if view.kind != "open" or not view.task or not tid:
            continue
        gate = dependency_gate(cfg, tid, cache=cache)
        if gate.blocked:
            assignments = dict(state.get("assignments") or {})
            cur = dict(assignments.get(pane) or info or {})
            sig = _blocked_signature(gate)
            prev = {
                "reason": cur.get("blocked_reason") or "",
                "blocked_on": list(cur.get("blocked_on") or []),
                "missing": list(cur.get("blocked_missing") or []),
                "cycle": list(cur.get("blocked_cycle") or []),
            }
            if prev != sig:
                cur["blocked_reason"] = sig["reason"]
                cur["blocked_on"] = sig["blocked_on"]
                cur["blocked_missing"] = sig["missing"]
                cur["blocked_cycle"] = sig["cycle"]
                cur["blocked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                assignments[pane] = cur
                state["assignments"] = assignments
                changed = True
                print(
                    f"blocked {tid} -> {cfg.session_name}:{pane} ({_blocked_prompt(gate)})",
                    file=sys.stderr,
                )
            continue
        assignments = dict(state.get("assignments") or {})
        cur = dict(assignments.get(pane) or info or {})
        if any(
            cur.get(key)
            for key in (
                "blocked_reason",
                "blocked_on",
                "blocked_missing",
                "blocked_cycle",
            )
        ):
            cur.pop("blocked_reason", None)
            cur.pop("blocked_on", None)
            cur.pop("blocked_missing", None)
            cur.pop("blocked_cycle", None)
            cur.pop("blocked_at", None)
            # drop legacy keys if present
            cur.pop("blocked_orphans", None)
            cur.pop("blocked_human_park", None)
            assignments[pane] = cur
            state["assignments"] = assignments
            changed = True
        health = cur.get("healthcheck") if isinstance(cur.get("healthcheck"), dict) else None
        if health and health.get("nonce"):
            nonce = str(health["nonce"])
            if healthcheck_ponged(cfg, pane, nonce):
                if dry_run:
                    print(f"would clear healthcheck pong {tid} <- pane {pane}")
                    continue
                cur.pop("healthcheck", None)
                cur["idle_chases"] = 0
                cur["last_healthcheck_pong_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                assignments[pane] = cur
                state["assignments"] = assignments
                changed = True
                print(f"healthcheck pong {tid} <- {cfg.session_name}:{pane}")
                continue
            sent_at_raw = health.get("sent_at")
            sent_at = float(sent_at_raw) if sent_at_raw is not None else now
            if now - sent_at < cfg.tasks.healthcheck_timeout_secs:
                continue
            restarts = int(cur.get("healthcheck_restarts") or 0)
            if restarts >= cfg.tasks.healthcheck_max_restarts:
                if dry_run:
                    print(
                        f"would mark healthcheck exhausted {tid} -> pane {pane} "
                        f"(restarts={restarts})"
                    )
                    continue
                cur["healthcheck_exhausted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                cur.pop("healthcheck", None)
                assignments[pane] = cur
                state["assignments"] = assignments
                changed = True
                print(
                    f"warning: healthcheck budget exhausted for {tid} -> {cfg.session_name}:{pane}",
                    file=sys.stderr,
                )
                continue
            if dry_run:
                print(
                    f"would respawn {tid} -> pane {pane} "
                    f"(healthcheck timeout, restart {restarts + 1}/"
                    f"{cfg.tasks.healthcheck_max_restarts})"
                )
                continue
            try:
                respawn_task_pane(cfg, pane)
            except Exception as e:
                print(
                    f"warning: healthcheck respawn {tid} -> {cfg.session_name}:{pane} failed: {e}",
                    file=sys.stderr,
                )
                continue
            cur["healthcheck_restarts"] = restarts + 1
            cur["idle_chases"] = 0
            cur.pop("healthcheck", None)
            cur["last_respawn_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            task = BacklogTask(id=tid, title=str(view.task.get("title") or ""), status="")
            try:
                event_id = deliver_task_prompt(
                    cfg, pane, build_task_prompt(cfg, task, pane, "", chase=True), dry_run=False,
                    meta={"task_id": tid, "pane": pane, "chase": True, "respawn": True},
                )
                cur["last_chased_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                if event_id is not None:
                    cur["last_chase_event_id"] = event_id
            except Exception as e:
                print(
                    f"warning: post-respawn chase {tid} -> {cfg.session_name}:{pane} failed: {e}",
                    file=sys.stderr,
                )
            assignments[pane] = cur
            state["assignments"] = assignments
            changed = True
            print(f"respawned {tid} -> {cfg.session_name}:{pane}")
            continue
        if cur.get("healthcheck_exhausted_at"):
            continue
        if not chase_due(info, min_chase, now=now):
            continue
        if not pane_ready_for_prompt(cfg, pane):
            continue
        title = str(view.task.get("title") or (info or {}).get("title") or "")
        task = BacklogTask(
            id=tid, title=title, status=str(view.task.get("status") or ""), priority=""
        )
        # Chase uses short prompt (body unused); pass empty to avoid snapshot bloat.
        prompt = build_task_prompt(cfg, task, pane, "", chase=True)
        if dry_run:
            print(f"would chase {tid} -> pane {pane} (still assigned, pane idle)")
            idle_after = int(cur.get("idle_chases") or 0) + 1
            if idle_after >= cfg.tasks.healthcheck_chases:
                print(f"would healthcheck probe {tid} -> pane {pane}")
            event_id = None
        else:
            event_id = deliver_task_prompt(
                cfg, pane, prompt, dry_run=False,
                meta={"task_id": tid, "pane": pane, "chase": True},
            )
            assignments = dict(state.get("assignments") or {})
            cur = dict(assignments.get(pane) or info or {})
            cur["last_chased_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            cur["idle_chases"] = int(cur.get("idle_chases") or 0) + 1
            if event_id is not None:
                cur["last_chase_event_id"] = event_id
            if cur["idle_chases"] >= cfg.tasks.healthcheck_chases:
                cur["healthcheck"] = send_healthcheck(cfg, pane, tid, dry_run=False)
                print(f"healthcheck probe {tid} -> {cfg.session_name}:{pane}")
            assignments[pane] = cur
            state["assignments"] = assignments
            changed = True
            print(f"chased {tid} -> {cfg.session_name}:{pane} event_id={event_id}")
        actions.append(
            {"task_id": tid, "pane": pane, "event_id": event_id, "dry_run": dry_run, "chase": True}
        )
    if changed:
        save_state(cfg, state)
    return actions


def recover_assignments_from_backlog(
    cfg: SwarmConfig,
    state: dict,
    *,
    dry_run: bool = False,
    tasks: list[BacklogTask] | None = None,
    cache: dict | None = None,
) -> dict:
    """Rebuild local state from backlog for pane assignments matching this session/pane.

    Risk: local state.json is sole memory of pane↔task. If dispatcher restarts with
    empty state.json, backlog still has aiswarm:session:pane assignees but chase/claim
    won't pick them up (unassigned_only filters; chase only reads state).

    Fix: scan backlog for In Progress (or ingest) tasks assigned to our session's panes,
    rehydrate local state. Do NOT override existing local assignments (they take precedence).
    List rows already carry assignees (BACK-545), so no per-task detail fetch is needed here.
    """
    assignments = dict(state.get("assignments") or {})
    changed = False
    wanted = {
        claim_assignee(cfg, pane_spec.pane): pane_spec.pane
        for pane_spec in cfg.task_panes
        if pane_spec.pane not in assignments
    }
    if not wanted:
        return state
    tasks = tasks if tasks is not None else list_candidate_tasks(
        cfg, unassigned_only=False
    )
    found: dict[str, BacklogTask] = {}
    for task in tasks:
        if task.status.strip().lower() == "to do":
            continue
        for assignee in task.assignees:
            pane = wanted.get(assignee)
            if pane is not None and pane not in found:
                found[pane] = task

    for pane_spec in cfg.task_panes:
        pane = pane_spec.pane
        if pane in assignments:
            continue
        found_task = found.get(pane)
        if found_task:
            assignments[pane] = {
                "task_id": found_task.id,
                "title": found_task.title,
                "assignee": claim_assignee(cfg, pane),
                "recovered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event_id": None,
            }
            changed = True

    if changed:
        state["assignments"] = assignments
        if not dry_run:
            save_state(cfg, state)

    return state


def _claim_new_onto_free(
    cfg: SwarmConfig,
    state: dict,
    dry_run: bool,
    *,
    candidates: list[BacklogTask] | None = None,
    cache: dict[str, dict | None] | None = None,
) -> list[dict]:
    """Pair free panes with unassigned candidates (one each)."""
    actions: list[dict] = []
    free = free_task_panes(cfg, state)
    if not free:
        return actions
    candidates = list(candidates) if candidates is not None else list_candidate_tasks(cfg)
    assigned_ids = {
        (info or {}).get("task_id")
        for info in (state.get("assignments") or {}).values()
    }
    candidates = [t for t in candidates if t.id not in assigned_ids]
    max_n = cfg.tasks.max_inflight
    inflight = len(state.get("assignments") or {})
    cache = cache if cache is not None else {}
    for pane in free:
        if max_n and inflight >= max_n:
            break
        task: BacklogTask | None = None
        task_full: dict | None = None
        pane_assignee = claim_assignee(cfg, pane).strip().lower()
        while candidates:
            candidate_idx = -1
            for idx, c in enumerate(candidates):
                c_assignees = {a.strip().lower() for a in c.assignees}
                if pane_assignee in c_assignees:
                    candidate_idx = idx
                    break
            if candidate_idx == -1:
                for idx, c in enumerate(candidates):
                    if not c.assignees:
                        candidate_idx = idx
                        break
            if candidate_idx == -1:
                break
            candidate = candidates.pop(candidate_idx)
            try:
                full = _task_or_none(cfg, candidate.id, cache)
            except Exception as e:
                # Fail closed: a transient fetch error must not be treated as
                # "skip_assignees can't apply, safe to claim." Skip this
                # candidate instead of silently claiming it.
                print(
                    f"skip claim {candidate.id}: task detail fetch failed, "
                    f"cannot verify skip_assignees: {e}",
                    file=sys.stderr,
                )
                continue
            if full is None:
                # Not found (or unrecoverable fetch failure cached as None):
                # same fail-closed reasoning as above.
                print(
                    f"skip claim {candidate.id}: task detail unavailable "
                    f"(not found or fetch error); cannot verify skip_assignees",
                    file=sys.stderr,
                )
                continue
            if task_skipped_for_claim(cfg, full):
                print(
                    f"skip claim {candidate.id}: assignee in skip_assignees "
                    f"{_task_assignees(full)}",
                    file=sys.stderr,
                )
                continue
            gate = dependency_gate(cfg, candidate.id, cache=cache)
            if gate.blocked:
                print(
                    f"skip claim {candidate.id}: {_blocked_prompt(gate)}",
                    file=sys.stderr,
                )
                continue
            task = candidate
            task_full = full
            break
        if task is None:
            break
        try:
            body = (
                format_task_snapshot(task_full)
                if not dry_run
                else f"(dry-run snapshot for {task.id})"
            )
        except Exception as e:
            body = f"(could not load task body: {e})"
        prompt = build_task_prompt(cfg, task, pane, body, chase=False)
        try:
            assignee = claim_task(cfg, task.id, pane, dry_run=dry_run)
        except Exception as e:
            print(f"warning: claim {task.id} -> {cfg.session_name}:{pane} failed: {e}", file=sys.stderr)
            continue
        if dry_run:
            print(
                f"would claim {task.id} -> pane {pane} assignee={assignee} "
                f"and deliver via {'log' if cfg.tasks.via_log else 'direct'}"
            )
            event_id = None
        else:
            assignments = dict(state.get("assignments") or {})
            assignments[pane] = {
                "task_id": task.id,
                "title": task.title,
                "assignee": assignee,
                "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            state["assignments"] = assignments
            state["last_dispatch"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_state(cfg, state)
            inflight = len(assignments)
            try:
                event_id = deliver_task_prompt(
                    cfg, pane, prompt, dry_run=False,
                    meta={"task_id": task.id, "pane": pane, "assignee": assignee},
                )
            except Exception as e:
                print(
                    f"warning: delivery {task.id} -> {cfg.session_name}:{pane} failed after claim; "
                    f"assignment retained for chase: {e}",
                    file=sys.stderr,
                )
                continue
            if event_id is not None:
                assignments[pane]["event_id"] = event_id
                save_state(cfg, state)
            print(f"dispatched {task.id} -> {cfg.session_name}:{pane} event_id={event_id}")
        actions.append(
            {
                "task_id": task.id,
                "pane": pane,
                "assignee": assignee,
                "event_id": event_id,
                "dry_run": dry_run,
                "chase": False,
            }
        )
    return actions


def _call_reconcile_assignments(cfg: SwarmConfig, state: dict, cache: dict | None) -> dict:
    import inspect
    try:
        sig = inspect.signature(reconcile_assignments)
        if "cache" in sig.parameters:
            return reconcile_assignments(cfg, state, cache=cache)
    except Exception:
        pass
    return reconcile_assignments(cfg, state)


def _call_chase_assigned(cfg: SwarmConfig, state: dict, dry_run: bool, cache: dict | None) -> list[dict]:
    import inspect
    try:
        sig = inspect.signature(chase_assigned)
        if "cache" in sig.parameters:
            return chase_assigned(cfg, state, dry_run=dry_run, cache=cache)
    except Exception:
        pass
    return chase_assigned(cfg, state, dry_run=dry_run)


def dispatch_once(cfg: SwarmConfig, dry_run: bool = False) -> list[dict]:
    """One pass: recover lost assignments → reconcile → chase open work → claim new unassigned work."""
    validate_tasks_config(cfg)
    assert cfg.tasks is not None
    if dry_run:
        print_effective_tasks(cfg)
    tasks = list_candidate_tasks(cfg, unassigned_only=False)
    # Shared per-pass cache: dependency_gate/view_assignment/_task_or_none all key off
    # task id, so reconcile, chase, and claim-gating reuse one detail fetch per task.
    cache: dict[str, dict | None] = {}
    state = recover_assignments_from_backlog(
        cfg, load_state(cfg), dry_run=dry_run, tasks=tasks
    )
    state = _call_reconcile_assignments(cfg, state, cache)
    actions = _call_chase_assigned(cfg, state, dry_run, cache)
    if not dry_run:
        state = load_state(cfg)
    # unassigned_only filter uses list-row assignees; no detail fetch needed here.
    if cfg.tasks.unassigned_only:
        our_assignees = {claim_assignee(cfg, pane_spec.pane).strip().lower() for pane_spec in cfg.task_panes}
        candidates = []
        for t in tasks:
            if not t.assignees:
                candidates.append(t)
            elif t.status.strip().lower() == "to do" and any(a.strip().lower() in our_assignees for a in t.assignees):
                candidates.append(t)
    else:
        candidates = list(tasks)
    actions.extend(
        _claim_new_onto_free(
            cfg, state, dry_run, candidates=candidates, cache=cache
        )
    )
    return actions


def start_dispatcher(cfg: SwarmConfig, dry_run: bool = False) -> None:
    validate_tasks_config(cfg)
    tasks_runtime_dir(cfg).mkdir(parents=True, exist_ok=True)
    wanted = desired_spec(cfg)
    if dry_run:
        print(
            f"would enable tasks group in session worker session={cfg.session_name} "
            f"panes={[p.pane for p in cfg.task_panes]} "
            f"backlog_dir={cfg.tasks.backlog_dir} "
            f"ingest={cfg.tasks.ingest}"
        )
        print_effective_tasks(cfg)
        return
    # The worker also owns comms, so ensure it exists before enabling the group.
    try:
        from . import babysitctl
    except ImportError:
        import babysitctl
    babysitctl.ensure_workers(cfg, dry_run=False)
    spec_path(cfg).write_text(json.dumps(wanted, indent=2) + "\n")
    enabled_path(cfg).write_text(json.dumps({"enabled": True}) + "\n")
    write_runtime_map(cfg)
    print(f"Enabled tasks group in session worker for {cfg.session_name}")


def stop_dispatcher(cfg: SwarmConfig, dry_run: bool = False) -> None:
    if dry_run:
        print(f"would disable tasks group in session worker for {cfg.session_name}")
        return
    enabled_path(cfg).unlink(missing_ok=True)
    print(f"Disabled tasks group in session worker for {cfg.session_name}")


def status(cfg: SwarmConfig) -> None:
    t = cfg.tasks
    enabled = enabled_path(cfg).exists()
    try:
        from .babysitctl import supervisor_pid_path
    except ImportError:
        from babysitctl import supervisor_pid_path
    path = supervisor_pid_path(cfg)
    pid = _read_pid(path) if path.exists() else 0
    alive = process_running(pid) if pid else False
    if enabled and alive:
        tasks_state = f"ON  (session worker pid={pid} running)"
    elif enabled:
        tasks_state = "OFF (tasks enabled but session worker is dead — restart with: aiswarm tasks start)"
    else:
        tasks_state = "OFF (tasks group disabled — aiswarm tasks start)"
    print(f"tasks:   {tasks_state}")
    print(f"session: {cfg.session_name}")
    print(f"config:  {cfg.path}")
    print(f"source:  {t.source}")
    try:
        bdir = ensure_backlog_dir(cfg)
    except Exception as e:
        bdir = f"(unresolved: {e})"
    print(f"backlog: {bdir}")
    print(f"ingest:  {t.ingest}")
    print(f"skip_assignees: {t.skip_assignees}")
    print(
        f"poll:    {t.poll_secs}s  min_chase={t.min_chase_secs}s  "
        f"unassigned_only={t.unassigned_only} "
        f"require_label={t.require_label!r} require_idle={t.require_idle}"
    )
    panes = cfg.task_panes
    print(f"task panes ({len(panes)}): " + (
        ", ".join(f"{p.pane}({p.title})" for p in panes) if panes else "(none)"
    ))
    if path.exists():
        print(f"dispatcher: pid={pid} {'running' if alive else 'dead'}")
    else:
        print("dispatcher: not started")
    state = load_state(cfg)
    assignments = state.get("assignments") or {}
    free = free_task_panes(cfg, state)
    print(f"free panes: {free if free else '(none)'}")
    if assignments:
        print("assignments:")
        for pane, info in sorted(assignments.items()):
            print(
                f"  {pane}: {info.get('task_id')} "
                f"assignee={info.get('assignee')} claimed_at={info.get('claimed_at')} "
                f"last_chased_at={info.get('last_chased_at')}"
            )
    else:
        print("assignments: (none)")
    # Status display only: preview candidates. Only the displayed rows are
    # dependency-gated (transitive closure per task is too costly to run over
    # the full candidate list just for a 15-line preview).
    if t and panes:
        try:
            cands = list_candidate_tasks(cfg)
            shown = cands[:15]
            cache: dict[str, dict | None] = {}
            gates = {c.id: dependency_gate(cfg, c.id, cache=cache) for c in shown}
            ready = sum(gate.ready for gate in gates.values())
            print(
                f"candidates ({len(cands)}; showing {len(shown)}: "
                f"ready {ready}, blocked {len(shown) - ready}):"
            )
            for c in shown:
                pri = f"[{c.priority}] " if c.priority else ""
                gate = gates[c.id]
                suffix = "ready" if gate.ready else f"blocked: {_blocked_prompt(gate)}"
                print(f"  {pri}{c.id} - {c.title} ({c.status}; {suffix})")
            if len(cands) > 15:
                print(f"  ... +{len(cands) - 15} more")
        except Exception as e:
            print(f"candidates: error: {e}")
