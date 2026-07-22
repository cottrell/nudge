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
import signal
import secrets
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
        get_events,
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
        get_events,
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
    """Atomic write (temp file + rename) so a crash mid-write can't truncate state.json."""
    tasks_runtime_dir(cfg).mkdir(parents=True, exist_ok=True)
    path = state_path(cfg)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
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
        f"   - Unassign yourself: backlog task edit {task.id} -a '' (or use backlog UI)\n"
        f"   - Optionally move to To Do: backlog task edit {task.id} -s 'To Do'\n"
        f"   - Task returns to dispatch pool for another pane\n"
        "5. Prefer durable aiswarm log messaging if you need help from other panes.\n"
        "\n"
        "--- task snapshot ---\n"
        f"{body}\n"
        "--- end snapshot ---\n"
    )


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


def send_healthcheck(cfg: SwarmConfig, pane: str, task_id: str) -> dict:
    nonce = secrets.token_urlsafe(12)
    payload = (
        f"HEALTHCHECK for assigned task {task_id}. If you can read this, reply now with:\n"
        f"aiswarm healthcheck pong {pane} {nonce}\n"
        "This is a one-off stall check, not a continuous heartbeat."
    )
    event_id = log_send(
        cfg.session_name,
        pane,
        payload,
        sender="tasks-dispatch",
        etype="healthcheck",
        meta={"task_id": task_id, "pane": pane, "nonce": nonce},
    )
    return {"nonce": nonce, "sent_at": time.time(), "event_id": event_id}


def respawn_task_pane(cfg: SwarmConfig, pane: str) -> None:
    """Restart one configured pane and attach a fresh activity monitor."""
    pane_spec = next(p for p in cfg.task_panes if p.pane == pane)
    target = pane_spec.target(cfg.session_name)
    subprocess.run(["tmux", "pipe-pane", "-t", target, ""], check=False, text=True)
    monitor_socket_path(cfg.session_name, pane).unlink(missing_ok=True)
    subprocess.run(
        ["tmux", "respawn-pane", "-k", "-t", target, "--", pane_spec.command],
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


def view_assignment(cfg: SwarmConfig, pane: str, task_id: str | None) -> AssignmentView:
    """How this assignment looks now. Used by reconcile + chase (do not duplicate)."""
    if not task_id:
        return AssignmentView("empty", reason="no_task_id")
    try:
        task = view_task_json(cfg, task_id)
    except RuntimeError as e:
        err = str(e).lower()
        if "not found" in err:
            return AssignmentView("missing", reason="not_found")
        return AssignmentView("error", reason=str(e))
    status = str(task.get("status") or "").strip().lower()
    if status == "done":
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


def reconcile_assignments(cfg: SwarmConfig, state: dict) -> dict:
    """Drop assignments that are done / missing / no longer assigned to this pane."""
    assignments = dict(state.get("assignments") or {})
    changed = False
    for pane, info in list(assignments.items()):
        tid = (info or {}).get("task_id")
        view = view_assignment(cfg, pane, tid)
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


def chase_assigned(cfg: SwarmConfig, state: dict, dry_run: bool = False) -> list[dict]:
    """Re-prompt idle panes that still own an open assignment (until Done/unassign/gone).

    Throttled by tasks.min_chase_secs (default = poll_secs: one chase opportunity per pass).
    """
    actions: list[dict] = []
    changed = False
    min_chase = cfg.tasks.min_chase_secs
    now = time.time()
    for pane, info in list((state.get("assignments") or {}).items()):
        tid = (info or {}).get("task_id")
        view = view_assignment(cfg, pane, tid)
        if view.kind in ("done", "missing", "unassigned", "empty"):
            _clear_assignment(state, pane, tid or "", view.reason or view.kind)
            changed = True
            continue
        if view.kind != "open" or not view.task or not tid:
            continue
        assignments = dict(state.get("assignments") or {})
        cur = dict(assignments.get(pane) or info or {})
        health = cur.get("healthcheck") if isinstance(cur.get("healthcheck"), dict) else None
        if health and health.get("nonce"):
            nonce = str(health["nonce"])
            if healthcheck_ponged(cfg, pane, nonce):
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
                cur["healthcheck"] = send_healthcheck(cfg, pane, tid)
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


def recover_assignments_from_backlog(cfg: SwarmConfig, state: dict) -> dict:
    """Rebuild local state from backlog for pane assignments matching this session/pane.

    Risk: local state.json is sole memory of pane↔task. If dispatcher restarts with
    empty state.json, backlog still has aiswarm:session:pane assignees but chase/claim
    won't pick them up (unassigned_only filters; chase only reads state).

    Fix: scan backlog for In Progress (or ingest) tasks assigned to our session's panes,
    rehydrate local state. Do NOT override existing local assignments (they take precedence).
    """
    assignments = dict(state.get("assignments") or {})
    changed = False

    # For each pane, search backlog for tasks assigned to this pane via claim_assignee prefix
    for pane_spec in cfg.task_panes:
        pane = pane_spec.pane
        if pane in assignments:
            continue  # Local assignment exists; do not override

        want_assignee = claim_assignee(cfg, pane)

        # Search all ingest statuses for tasks with matching assignee
        found_task: BacklogTask | None = None
        for status in cfg.tasks.ingest:
            args = ["task", "list", "-s", status, "--json", "--limit", "200"]
            if cfg.tasks.require_label:
                args.extend(["-l", cfg.tasks.require_label])
            try:
                proc = _run_backlog(cfg, args)
                data = _json_or_raise(proc, f"backlog recovery task list status={status!r}")
                tasks = parse_task_list_json(data)

                # Find first task assigned to this pane
                for task in tasks:
                    try:
                        full_task = view_task_json(cfg, task.id)
                        assignees = full_task.get("assignees") or []
                        if isinstance(assignees, str):
                            assignees = [assignees]
                        if want_assignee in assignees:
                            found_task = task
                            break
                    except Exception:
                        continue

                if found_task:
                    break
            except Exception:
                continue

        if found_task:
            assignments[pane] = {
                "task_id": found_task.id,
                "title": found_task.title,
                "assignee": want_assignee,
                "recovered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event_id": None,
            }
            changed = True

    if changed:
        state["assignments"] = assignments
        save_state(cfg, state)

    return state


def _claim_new_onto_free(
    cfg: SwarmConfig, state: dict, dry_run: bool
) -> list[dict]:
    """Pair free panes with unassigned candidates (one each)."""
    actions: list[dict] = []
    free = free_task_panes(cfg, state)
    if not free:
        return actions
    candidates = list_candidate_tasks(cfg)
    assigned_ids = {
        (info or {}).get("task_id")
        for info in (state.get("assignments") or {}).values()
    }
    candidates = [t for t in candidates if t.id not in assigned_ids]
    max_n = cfg.tasks.max_inflight
    inflight = len(state.get("assignments") or {})
    for pane in free:
        if max_n and inflight >= max_n:
            break
        if not candidates:
            break
        task = candidates.pop(0)
        try:
            body = (
                view_task_plain(cfg, task.id)
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


def dispatch_once(cfg: SwarmConfig, dry_run: bool = False) -> list[dict]:
    """One pass: recover lost assignments → reconcile → chase open work → claim new unassigned work."""
    validate_tasks_config(cfg)
    assert cfg.tasks is not None
    if dry_run:
        print_effective_tasks(cfg)
    state = recover_assignments_from_backlog(cfg, load_state(cfg))
    state = reconcile_assignments(cfg, state)
    actions = chase_assigned(cfg, state, dry_run=dry_run)
    state = load_state(cfg)
    actions.extend(_claim_new_onto_free(cfg, state, dry_run))
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
            [sys.executable, str(Path(__file__).resolve().parent / "tasks_dispatch.py"), str(cfg.path)],
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
    try:
        bdir = ensure_backlog_dir(cfg)
    except Exception as e:
        bdir = f"(unresolved: {e})"
    print(f"backlog: {bdir}")
    print(f"ingest:  {t.ingest}")
    print(
        f"poll:    {t.poll_secs}s  min_chase={t.min_chase_secs}s  "
        f"unassigned_only={t.unassigned_only} "
        f"require_label={t.require_label!r} require_idle={t.require_idle}"
    )
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
    # Status display only: preview candidates (cap lines; full list still used by dispatch).
    if t and panes:
        try:
            cands = list_candidate_tasks(cfg)
            print(f"candidates ({len(cands)}):")
            for c in cands[:15]:  # display cap only
                pri = f"[{c.priority}] " if c.priority else ""
                print(f"  {pri}{c.id} - {c.title} ({c.status})")
            if len(cands) > 15:
                print(f"  ... +{len(cands) - 15} more")
        except Exception as e:
            print(f"candidates: error: {e}")
