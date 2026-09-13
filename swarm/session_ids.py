#!/usr/bin/env python3
"""Bind tmux panes to provider-native session IDs.

Mint at launch when the CLI accepts --session-id (claude, grok). Otherwise
discover from this pane's process: argv, pid-keyed files, open fds.
Never use newest-file-in-cwd — that collides when many panes start together.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import uuid

try:
    from .common import SwarmConfig
except ImportError:
    from common import SwarmConfig


UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)

_AGENT_ALIAS = {
    "antigravity": "agy",
    "agy": "agy",
    "claude": "claude",
    "codex": "codex",
    "grok": "grok",
    "gemini": "gemini",
    "vibe": "vibe",
    "qwen": "qwen",
    "copilot": "copilot",
}

# Flags that already pin or resume a conversation — do not mint over them.
_SESSION_FLAGS = {
    "claude": ("--session-id", "--resume", "-r", "--continue"),
    "grok": ("--session-id", "-s", "--resume", "-r", "--continue", "-c"),
    "codex": ("resume",),
    "agy": ("--conversation", "--continue", "-c"),
    "gemini": ("--resume", "--continue", "-c"),
    "vibe": ("--resume", "--continue", "-c"),
}

_ID_FLAGS = ("--session-id", "-s", "--resume", "-r", "--conversation")
_MINTABLE = frozenset({"claude", "grok"})


def canonical_agent(agent: str | None) -> str:
    return _AGENT_ALIAS.get((agent or "").strip().lower(), (agent or "").strip().lower())


def new_session_id() -> str:
    return str(uuid.uuid4())


def resume_command(agent: str, session_id: str) -> str:
    agent = canonical_agent(agent)
    sid = session_id.strip()
    if agent == "claude":
        return f"claude -r {sid}"
    if agent == "grok":
        return f"grok -r {sid}"
    if agent == "codex":
        return f"codex resume {sid}"
    if agent == "agy":
        return f"agy --conversation {sid}"
    if agent == "gemini":
        return f"gemini --resume {sid}"
    if agent == "vibe":
        return f"vibe --resume {sid}"
    return f"{agent} --resume {sid}" if agent else ""


def runtime_records_path(cfg: SwarmConfig) -> Path:
    return cfg.runtime_dir / "session-ids.json"


def durable_records_path(cfg: SwarmConfig) -> Path:
    return cfg.path.parent / "session-ids.json"


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _argv_has_session_control(agent: str, argv: list[str]) -> bool:
    flags = _SESSION_FLAGS.get(agent, ())
    lower = [a.lower() if agent == "codex" else a for a in argv]
    if agent == "codex":
        return "resume" in lower
    return any(a in flags for a in argv)


def mint_launch_command(agent: str | None, command: str) -> tuple[str, str | None, str]:
    """Return (command, session_id, source). source is minted|argv|''."""
    agent = canonical_agent(agent)
    if agent not in _MINTABLE or not (command or "").strip():
        return command, None, ""
    argv = _split_command(command)
    if _argv_has_session_control(agent, argv):
        existing = session_id_from_argv(agent, argv)
        return command, existing, "argv" if existing else ""
    sid = new_session_id()
    return f"{command.rstrip()} --session-id {sid}", sid, "minted"


def session_id_from_argv(agent: str, argv: list[str]) -> str | None:
    agent = canonical_agent(agent)
    if agent == "codex":
        for i, tok in enumerate(argv):
            if tok.lower() == "resume" and i + 1 < len(argv):
                for cand in argv[i + 1 :]:
                    if UUID_RE.fullmatch(cand):
                        return cand
                return None
        return None
    for i, tok in enumerate(argv):
        if tok in _ID_FLAGS and i + 1 < len(argv):
            cand = argv[i + 1]
            if cand.startswith("-"):
                continue
            if UUID_RE.fullmatch(cand) or tok in ("--session-id", "-s", "--conversation"):
                return cand
    return None


def child_pids(pid: int, proc_root: Path) -> list[int]:
    out: list[int] = []
    task_dir = proc_root / str(pid) / "task"
    if not task_dir.is_dir():
        return out
    for task in task_dir.iterdir():
        children = task / "children"
        if not children.is_file():
            continue
        try:
            text = children.read_text()
        except OSError:
            continue
        for part in text.split():
            if part.isdigit():
                n = int(part)
                if n not in out:
                    out.append(n)
    return out


def process_tree(root_pid: int, proc_root: Path, limit: int = 64) -> list[int]:
    seen: list[int] = []
    queue = [root_pid]
    while queue and len(seen) < limit:
        pid = queue.pop(0)
        if pid in seen or pid <= 0:
            continue
        seen.append(pid)
        queue.extend(child_pids(pid, proc_root))
    return seen


def cmdline_of(pid: int, proc_root: Path) -> list[str]:
    path = proc_root / str(pid) / "cmdline"
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    return [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]


def open_paths(pid: int, proc_root: Path) -> list[str]:
    fd_dir = proc_root / str(pid) / "fd"
    if not fd_dir.is_dir():
        return []
    paths: list[str] = []
    try:
        entries = list(fd_dir.iterdir())
    except OSError:
        return []
    for entry in entries:
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if target.startswith("/"):
            paths.append(target)
    return paths


def _claude_pid_file_id(pid: int, home: Path) -> str | None:
    path = home / ".claude" / "sessions" / f"{pid}.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    sid = data.get("sessionId") or data.get("session_id") or data.get("id")
    return str(sid) if sid else None


def _load_grok_active(home: Path) -> dict[int, str]:
    path = home / ".grok" / "active_sessions.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[int, str] = {}
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        pid = item.get("pid")
        sid = item.get("session_id") or item.get("sessionId")
        if isinstance(pid, int) and sid:
            out[pid] = str(sid)
    return out


def session_id_from_path(agent: str, path: str) -> str | None:
    agent = canonical_agent(agent)
    base = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    if agent == "grok":
        if "/.grok/sessions/" not in path.replace("\\", "/"):
            return None
        # .../sessions/<cwd-enc>/<uuid>/events.jsonl
        parts = Path(path).parts
        for i, part in enumerate(parts):
            if part == "sessions" and i + 2 < len(parts):
                cand = parts[i + 2]
                if UUID_RE.fullmatch(cand):
                    return cand
        return None
    if agent == "agy":
        if parent in ("conversations", "presence"):
            stem = base.split(".")[0]
            if UUID_RE.fullmatch(stem):
                return stem
        return None
    if agent == "codex":
        if base.startswith("rollout-") and base.endswith(".jsonl"):
            m = UUID_RE.findall(base)
            return m[-1] if m else None
        return None
    if agent == "claude":
        if parent == "projects" or path.replace("\\", "/").find("/.claude/projects/") >= 0:
            stem = base[:-6] if base.endswith(".jsonl") else ""
            if UUID_RE.fullmatch(stem):
                return stem
        return None
    return None


@dataclass
class SessionRecord:
    pane: str
    agent: str
    session_id: str | None
    source: str
    pid: int | None = None
    resume: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "id": self.session_id,
            "source": self.source,
            "pid": self.pid,
            "resume": self.resume,
            "updated_at": self.updated_at,
        }


def record_from_dict(pane: str, data: dict) -> SessionRecord:
    agent = canonical_agent(str(data.get("agent") or ""))
    sid = data.get("id") or data.get("session_id")
    sid_s = str(sid) if sid else None
    return SessionRecord(
        pane=pane,
        agent=agent,
        session_id=sid_s,
        source=str(data.get("source") or ""),
        pid=data.get("pid") if isinstance(data.get("pid"), int) else None,
        resume=str(data.get("resume") or (resume_command(agent, sid_s) if sid_s else "")),
        updated_at=str(data.get("updated_at") or ""),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_session_id(
    agent: str | None,
    root_pid: int | None,
    *,
    home: Path | None = None,
    proc_root: Path | None = None,
) -> tuple[str | None, str, int | None]:
    """Return (session_id, source, matched_pid). source is '' if unknown."""
    agent = canonical_agent(agent)
    if not agent or not root_pid or root_pid <= 0:
        return None, "", None
    home = home or Path.home()
    proc_root = proc_root or Path("/proc")
    tree = process_tree(root_pid, proc_root)
    grok_active = _load_grok_active(home) if agent == "grok" else {}

    for pid in tree:
        argv = cmdline_of(pid, proc_root)
        sid = session_id_from_argv(agent, argv)
        if sid:
            return sid, "argv", pid

    if agent == "claude":
        for pid in tree:
            sid = _claude_pid_file_id(pid, home)
            if sid:
                return sid, "pid_file", pid

    if agent == "grok":
        for pid in tree:
            sid = grok_active.get(pid)
            if sid:
                return sid, "active_sessions", pid

    for pid in tree:
        for path in open_paths(pid, proc_root):
            sid = session_id_from_path(agent, path)
            if sid:
                return sid, "proc_fd", pid

    return None, "", None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def load_records(cfg: SwarmConfig) -> dict[str, SessionRecord]:
    out: dict[str, SessionRecord] = {}
    for path in (durable_records_path(cfg), runtime_records_path(cfg)):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text() or "{}")
        except (OSError, json.JSONDecodeError):
            continue
        panes = data.get("panes") if isinstance(data, dict) else None
        if not isinstance(panes, dict):
            continue
        for pane, rec in panes.items():
            if isinstance(rec, dict):
                out[str(pane)] = record_from_dict(str(pane), rec)
    return out


def save_records(cfg: SwarmConfig, records: dict[str, SessionRecord]) -> None:
    payload = {
        "session_name": cfg.session_name,
        "updated_at": now_iso(),
        "panes": {pane: rec.as_dict() for pane, rec in sorted(records.items())},
    }
    text = json.dumps(payload, indent=2) + "\n"
    _atomic_write(runtime_records_path(cfg), text)
    _atomic_write(durable_records_path(cfg), text)


def merge_record(
    existing: SessionRecord | None,
    incoming: SessionRecord,
) -> SessionRecord:
    if existing is None:
        return incoming
    if incoming.session_id:
        return incoming
    return existing


def make_record(
    pane: str,
    agent: str | None,
    session_id: str | None,
    source: str,
    pid: int | None = None,
) -> SessionRecord:
    agent_c = canonical_agent(agent)
    return SessionRecord(
        pane=pane,
        agent=agent_c,
        session_id=session_id,
        source=source if session_id else "",
        pid=pid,
        resume=resume_command(agent_c, session_id) if session_id else "",
        updated_at=now_iso(),
    )


def refresh_records(
    cfg: SwarmConfig,
    pane_pids: dict[str, int],
    *,
    home: Path | None = None,
    proc_root: Path | None = None,
) -> dict[str, SessionRecord]:
    records = load_records(cfg)
    home = home or Path.home()
    proc_root = proc_root or Path("/proc")
    for pane in cfg.panes:
        if not pane.agent:
            continue
        pid = pane_pids.get(pane.pane)
        sid, source, matched = discover_session_id(
            pane.agent, pid, home=home, proc_root=proc_root
        )
        incoming = make_record(pane.pane, pane.agent, sid, source, matched or pid)
        records[pane.pane] = merge_record(records.get(pane.pane), incoming)
    save_records(cfg, records)
    return records


def format_records(cfg: SwarmConfig, records: dict[str, SessionRecord]) -> str:
    rows = [("pane", "agent", "source", "session_id", "resume")]
    for pane in cfg.panes:
        rec = records.get(pane.pane)
        agent = (rec.agent if rec else None) or pane.agent or "-"
        if rec and rec.session_id:
            rows.append(
                (
                    pane.pane,
                    agent,
                    rec.source or "-",
                    rec.session_id,
                    rec.resume or resume_command(agent, rec.session_id),
                )
            )
        elif pane.agent:
            rows.append((pane.pane, agent, rec.source if rec else "-", "-", "(no id yet)"))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    lines = []
    for i, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row))
        lines.append(line.rstrip())
        if i == 0:
            lines.append("  ".join("-" * widths[j] for j in range(5)))
    return "\n".join(lines)
