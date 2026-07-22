#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
SWARM_CLI = ROOT_DIR / "swarm" / "cli.py"
VALID_AGENTS = ("claude", "codex", "copilot", "gemini", "grok", "vibe", "qwen", "antigravity")
SHELL_NAMES = {"bash", "sh", "zsh", "fish"}
AGENT_STATS_CMD: dict[str, str | None] = {
    "claude":  "/usage",
    "codex":   "/status",
    "gemini":  "/stats",
    "antigravity": "/stats",
    "qwen":    "/stats",
    "grok":    None,
    "copilot": None,
    "vibe":    None,
}
PANE_RE = re.compile(r"^(\d+)\.(\d+)$")


# ---------------------------------------------------------------------------
# Default values live ONLY on these dataclasses.
# load_config() is the ONLY place that merges YAML + defaults → complete objects.
# Downstream code must use SwarmConfig fields; never re-apply defaults.
# ---------------------------------------------------------------------------


@dataclass
class BabysitSpec:
    enabled: bool = False
    interval_secs: int = 600
    clear_every: int = 0
    long_prompt: str = ""
    long_prompt_file: Path | None = None
    short_prompt: str = ""
    short_prompt_file: Path | None = None
    via_log: bool = True  # if False, send nudges directly instead of via comms log
    # EMA quota-pacing settings (see README § Quota pacing)
    quota_probe_secs: int = 300    # how often to sample quota (seconds)
    ema_alpha: float = 0.30        # EMA smoothing factor
    ema_safety: float = 0.92       # fraction of quota to target (leaves ~8% buffer)
    ema_k_var: float = 0.0         # variance weight; raise to 0.5–1.0 for conservative pacing
    ema_warmup: int = 3            # nudges before EMA replaces fixed interval
    ema_min_wait: int = 30         # hard floor (seconds)
    ema_max_wait: int = 1200       # hard ceiling (seconds)


@dataclass
class TasksSpec:
    """Session-level work dispatcher (source=backlog for v1; name stays source-agnostic)."""
    source: str = "backlog"
    backlog_dir: Path | None = None
    # Statuses to pull from the source. Default: only To Do (In Progress is opt-in).
    ingest: list[str] = field(default_factory=lambda: ["To Do", "In Progress"])
    poll_secs: int = 60
    require_label: str | None = None
    unassigned_only: bool = True
    claim_assignee_prefix: str = "aiswarm"
    via_log: bool = True
    max_inflight: int = 0  # 0 = unlimited (one task per free pane still)
    require_idle: bool = True
    # Min seconds between chase re-prompts per assignment (0 = always due).
    # Default tracks poll_secs so idle-assigned panes get poked each pass.
    min_chase_secs: int = 60


@dataclass
class PaneSpec:
    pane: str        # "W.N" — window index . pane index within window
    agent: str | None
    command: str
    title: str
    monitor: bool
    babysit: BabysitSpec
    comms: bool
    tasks_enabled: bool

    @property
    def pane_index(self) -> int:
        return int(PANE_RE.match(self.pane).group(2))

    @property
    def window_index(self) -> int:
        return int(PANE_RE.match(self.pane).group(1))

    def target(self, session_name: str) -> str:
        return f"{session_name}:{self.pane}"


@dataclass
class WindowSpec:
    window_name: str
    layout: str
    panes: list[PaneSpec]


@dataclass
class SwarmConfig:
    path: Path
    session_name: str
    windows: list[WindowSpec]
    tasks: TasksSpec  # always filled by load_config

    @property
    def window_name(self) -> str:
        return self.windows[0].window_name

    @property
    def panes(self) -> list[PaneSpec]:
        return [p for w in self.windows for p in w.panes]

    @property
    def pane_count(self) -> int:
        return sum(len(w.panes) for w in self.windows)

    @property
    def runtime_dir(self) -> Path:
        return Path("/tmp/nudge-swarm") / self.session_name

    @property
    def runtime_map_path(self) -> Path:
        return self.runtime_dir / "runtime.json"

    @property
    def task_panes(self) -> list[PaneSpec]:
        return [p for p in self.panes if p.tasks_enabled]


def resolve_backlog_dir(cfg_path: Path, explicit: str | None) -> Path:
    """Resolve backlog directory: explicit path, else walk up for backlog/config.yml."""
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = (cfg_path.parent / p).resolve()
        else:
            p = p.resolve()
        if not (p / "config.yml").exists() and not p.is_dir():
            raise ValueError(f"tasks.backlog_dir not found: {p}")
        if not p.is_dir():
            raise ValueError(f"tasks.backlog_dir is not a directory: {p}")
        return p
    for base in [cfg_path.parent, *cfg_path.parent.parents]:
        cand = base / "backlog"
        if (cand / "config.yml").exists():
            return cand.resolve()
    raise ValueError(
        "tasks.backlog_dir not set and no backlog/config.yml found above config path; "
        "set tasks.backlog_dir in the swarm YAML"
    )


def _fill_babysit(raw: dict | None, pane_id: str, cfg_path: Path) -> BabysitSpec:
    """Merge raw babysit YAML onto BabysitSpec() defaults. Called only from load_config."""
    d = BabysitSpec()
    raw = raw or {}
    long_prompt_file = raw.get("long_prompt_file") or raw.get("prompt_file")
    short_prompt_file = raw.get("short_prompt_file")
    long_prompt = str(raw.get("long_prompt") or raw.get("prompt") or d.long_prompt)
    short_prompt = str(raw.get("short_prompt") or d.short_prompt)
    long_prompt_path = d.long_prompt_file
    short_prompt_path = d.short_prompt_file
    if long_prompt_file:
        long_prompt_path = (cfg_path.parent / str(long_prompt_file)).resolve()
        if not long_prompt_path.exists():
            raise ValueError(f"pane {pane_id} long_prompt_file not found: {long_prompt_file}")
        if not long_prompt:
            long_prompt = long_prompt_path.read_text()
    if short_prompt_file:
        short_prompt_path = (cfg_path.parent / str(short_prompt_file)).resolve()
        if not short_prompt_path.exists():
            raise ValueError(f"pane {pane_id} short_prompt_file not found: {short_prompt_file}")
        if not short_prompt:
            short_prompt = short_prompt_path.read_text()
    if not short_prompt:
        short_prompt = long_prompt
    return BabysitSpec(
        enabled=bool(raw.get("enabled", d.enabled)),
        interval_secs=int(raw.get("interval_secs", d.interval_secs)),
        clear_every=int(raw.get("clear_every", d.clear_every)),
        long_prompt=long_prompt,
        long_prompt_file=long_prompt_path,
        short_prompt=short_prompt,
        short_prompt_file=short_prompt_path,
        via_log=bool(raw.get("via_log", d.via_log)),
        quota_probe_secs=int(raw.get("quota_probe_secs", d.quota_probe_secs)),
        ema_alpha=float(raw.get("ema_alpha", d.ema_alpha)),
        ema_safety=float(raw.get("ema_safety", d.ema_safety)),
        ema_k_var=float(raw.get("ema_k_var", d.ema_k_var)),
        ema_warmup=int(raw.get("ema_warmup", d.ema_warmup)),
        ema_min_wait=int(raw.get("ema_min_wait", d.ema_min_wait)),
        ema_max_wait=int(raw.get("ema_max_wait", d.ema_max_wait)),
    )


def _fill_tasks(raw: dict | None, cfg_path: Path) -> TasksSpec:
    """Merge raw tasks YAML onto TasksSpec() defaults. Called only from load_config."""
    d = TasksSpec()
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("tasks must be a mapping")
    source = str(raw.get("source") or d.source).strip().lower()
    if source != "backlog":
        raise ValueError(f"tasks.source={source!r} not supported yet (v1: backlog only)")
    if "ingest" in raw:
        ingest_raw = raw.get("ingest")
        if isinstance(ingest_raw, str):
            ingest = [s.strip() for s in ingest_raw.split(",") if s.strip()]
        else:
            ingest = [str(s).strip() for s in (ingest_raw or []) if str(s).strip()]
    else:
        ingest = list(d.ingest)
    if not ingest:
        raise ValueError("tasks.ingest must list at least one status")
    require_label = raw.get("require_label", d.require_label)
    require_label = str(require_label).strip() if require_label else None
    # backlog_dir is a source-adapter detail (v1: backlog). Only store explicit YAML;
    # walk-up discovery happens when the backlog source actually runs.
    explicit_dir = raw.get("backlog_dir")
    backlog_dir = (
        resolve_backlog_dir(cfg_path, str(explicit_dir).strip())
        if explicit_dir
        else d.backlog_dir
    )
    poll_secs = max(5, int(raw.get("poll_secs", d.poll_secs)))
    # Default chase interval = poll so each dispatcher pass may re-nudge idle assigned work.
    min_chase_secs = max(
        0, int(raw["min_chase_secs"]) if "min_chase_secs" in raw else poll_secs
    )
    return TasksSpec(
        source=source,
        backlog_dir=backlog_dir,
        ingest=ingest,
        poll_secs=poll_secs,
        require_label=require_label,
        unassigned_only=bool(raw.get("unassigned_only", d.unassigned_only)),
        claim_assignee_prefix=str(
            raw.get("claim_assignee_prefix") or d.claim_assignee_prefix
        ).strip(),
        via_log=bool(raw.get("via_log", d.via_log)),
        max_inflight=max(0, int(raw.get("max_inflight", d.max_inflight))),
        require_idle=bool(raw.get("require_idle", d.require_idle)),
        min_chase_secs=min_chase_secs,
    )


def _fill_pane(praw: dict | None, pane_id: str, cfg_path: Path) -> PaneSpec:
    """Merge one pane YAML onto complete PaneSpec. Called only from load_config."""
    praw = praw or {}
    nudge = praw.get("nudge") or {}

    agent = str(nudge.get("agent") or "").strip() or None
    monitor = bool(nudge.get("monitor", bool(agent)))
    if monitor and not agent:
        raise ValueError(f"pane {pane_id} requires nudge.agent when nudge.monitor=true")
    if agent and agent not in VALID_AGENTS:
        raise ValueError(f"unknown agent: {agent}")

    command = str(praw.get("shell_command") or "").strip() or "bash"
    title = str(nudge.get("title") or agent or pane_id).strip()

    babysit = _fill_babysit(nudge.get("babysit"), pane_id, cfg_path)
    if babysit.enabled and not monitor:
        raise ValueError(f"pane {pane_id} cannot enable babysit when monitor=false")

    # tasks_enabled default = monitor (on for agent panes; off for shell)
    tasks_raw = nudge.get("tasks") if isinstance(nudge.get("tasks"), dict) else {}
    tasks_enabled = bool(tasks_raw.get("enabled", monitor))
    if tasks_enabled and not monitor:
        raise ValueError(f"pane {pane_id} cannot enable tasks when monitor=false")

    # comms default = monitor
    comms_raw = nudge.get("comms") if isinstance(nudge.get("comms"), dict) else {}
    comms = bool(comms_raw.get("enabled", monitor))

    return PaneSpec(
        pane=pane_id,
        agent=agent,
        command=command,
        title=title,
        monitor=monitor,
        babysit=babysit,
        comms=comms,
        tasks_enabled=tasks_enabled,
    )


def effective_config_dict(cfg: SwarmConfig) -> dict:
    """Serialize already-filled SwarmConfig. Does not apply defaults."""
    t = cfg.tasks
    return {
        "session_name": cfg.session_name,
        "path": str(cfg.path),
        "tasks": {
            "source": t.source,
            "backlog_dir": str(t.backlog_dir) if t.backlog_dir else None,
            "ingest": list(t.ingest),
            "poll_secs": t.poll_secs,
            "unassigned_only": t.unassigned_only,
            "require_label": t.require_label,
            "require_idle": t.require_idle,
            "via_log": t.via_log,
            "max_inflight": t.max_inflight,
            "min_chase_secs": t.min_chase_secs,
            "claim_assignee_prefix": t.claim_assignee_prefix,
            "enabled_panes": [p.pane for p in cfg.task_panes],
        },
        "panes": [
            {
                "pane": p.pane,
                "title": p.title,
                "agent": p.agent,
                "command": p.command,
                "monitor": p.monitor,
                "comms": p.comms,
                "tasks_enabled": p.tasks_enabled,
                "babysit": {
                    "enabled": p.babysit.enabled,
                    "interval_secs": p.babysit.interval_secs,
                    "clear_every": p.babysit.clear_every,
                    "via_log": p.babysit.via_log,
                },
            }
            for p in cfg.panes
        ],
    }


# Default harness location for consumer projects (not package code).
# Resolve order for load_config(None) / CLI: explicit path > AISWARM_CONFIG > walk-up.
AISWARM_DIRNAME = ".aiswarm"
AISWARM_CONFIG_NAME = "config.yaml"
AISWARM_CONFIG_ENV = "AISWARM_CONFIG"


def looks_like_config_path(value: str | Path) -> bool:
    """True if value is an existing file or a *.yaml/*.yml path token."""
    s = str(value).strip()
    if not s:
        return False
    p = Path(s)
    if p.is_file():
        return True
    return s.endswith((".yaml", ".yml"))


def find_aiswarm_config(start: str | Path | None = None) -> Path | None:
    """Walk up from start (default: cwd) for `.aiswarm/config.yaml`."""
    base = Path(start or Path.cwd()).resolve()
    if base.is_file():
        base = base.parent
    for d in [base, *base.parents]:
        candidate = d / AISWARM_DIRNAME / AISWARM_CONFIG_NAME
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_config_path(
    explicit: str | Path | None = None,
    *,
    start: str | Path | None = None,
    env: dict | None = None,
) -> Path:
    """Resolve swarm YAML path.

    Order:
      1. explicit path (CLI positional or -c)
      2. AISWARM_CONFIG env
      3. walk-up `.aiswarm/config.yaml` from start/cwd
    """
    if explicit is not None and str(explicit).strip():
        path = Path(str(explicit).strip()).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"config not found: {path}")
        return path.resolve()

    environ = env if env is not None else os.environ
    env_val = (environ.get(AISWARM_CONFIG_ENV) or "").strip()
    if env_val:
        path = Path(env_val).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"{AISWARM_CONFIG_ENV}={env_val!r} but file not found"
            )
        return path.resolve()

    found = find_aiswarm_config(start)
    if found is not None:
        return found

    raise FileNotFoundError(
        "no aiswarm config: pass a path, set "
        f"{AISWARM_CONFIG_ENV}, or create {AISWARM_DIRNAME}/{AISWARM_CONFIG_NAME} "
        "(aiswarm init <name>)"
    )


def load_config(path: str | Path | None = None) -> SwarmConfig:
    """Load YAML and return a fully filled SwarmConfig.

    This is the ONLY entry point that applies defaults. All CLI/workers must use
    the returned objects; do not re-default fields elsewhere.
    """
    cfg_path = resolve_config_path(path)
    data = yaml.safe_load(cfg_path.read_text()) or {}

    session_name = str(data.get("session_name") or "").strip()
    if not session_name:
        raise ValueError("session_name is required")
    if ":" in session_name:
        raise ValueError("session_name must not contain ':'")

    windows_data = data.get("windows") or []
    if not windows_data:
        raise ValueError("windows is required and must not be empty")

    windows: list[WindowSpec] = []
    for win_idx, wraw in enumerate(windows_data):
        window_name = str(wraw.get("window_name") or "").strip()
        if not window_name:
            raise ValueError(f"windows[{win_idx}] missing window_name")
        layout = str(wraw.get("layout") or "tiled").strip()

        panes = [
            _fill_pane(praw, f"{win_idx}.{pane_idx}", cfg_path)
            for pane_idx, praw in enumerate(wraw.get("panes") or [])
        ]
        windows.append(WindowSpec(window_name=window_name, layout=layout, panes=panes))

    return SwarmConfig(
        path=cfg_path,
        session_name=session_name,
        windows=windows,
        tasks=_fill_tasks(data.get("tasks"), cfg_path),
    )


def monitor_socket_path(session_name: str, pane: str) -> Path:
    return Path(f"/tmp/{session_name}_{pane}.sock")


def babysit_runtime_paths(cfg: SwarmConfig, pane: str) -> dict[str, str]:
    # Legacy "babysit-" prefix for worker runtime files (pid/log/spec/state).
    # Kept for compatibility. This covers the single IO loop (comms base + optional
    # babysit prompt group).
    stem = f"babysit-{pane.replace('.', '-')}"
    return {
        "pid": str(cfg.runtime_dir / f"{stem}.pid"),
        "log": str(cfg.runtime_dir / f"{stem}.log"),
        "spec": str(cfg.runtime_dir / f"{stem}.json"),
        "state": str(cfg.runtime_dir / f"{stem}.state.json"),
    }


def build_runtime_map(cfg: SwarmConfig) -> dict:
    panes_map: dict[str, dict[str, object]] = {}
    for pane in cfg.panes:
        entry: dict[str, object] = {
            "target": pane.target(cfg.session_name),
            "socket": str(monitor_socket_path(cfg.session_name, pane.pane)) if pane.monitor else None,
        }
        if pane.babysit.enabled:
            bs_paths = babysit_runtime_paths(cfg, pane.pane)
            spec_file = Path(bs_paths["spec"])
            has_long = bool(pane.babysit.long_prompt)
            has_short = bool(pane.babysit.short_prompt)
            if spec_file.exists():
                try:
                    sp = json.loads(spec_file.read_text() or "{}")
                    has_long = bool(sp.get("long_prompt") or sp.get("short_prompt"))
                    has_short = has_long
                except Exception:
                    pass
            # Always advertise the babysit paths when configured in yaml.
            # has_* reflect the *deployed* spec (false if never started or disabled).
            # Consumers must check has_long_prompt/has_short_prompt (or pid+running)
            # rather than mere key presence. This was the root of stale "babysit running"
            # reports after babysit stop (fixed on the producer side here; old consumers
            # like some thoth views may still need updating).
            entry["babysit"] = {
                **bs_paths,
                "has_long_prompt": has_long,
                "has_short_prompt": has_short,
            }
        entry["tasks"] = {"enabled": pane.tasks_enabled}
        panes_map[pane.pane] = entry
    tdir = cfg.runtime_dir / "tasks"
    t = cfg.tasks
    tasks_info = {
        "source": t.source,
        "backlog_dir": str(t.backlog_dir) if t.backlog_dir else None,
        "ingest": list(t.ingest),
        "poll_secs": t.poll_secs,
        "min_chase_secs": t.min_chase_secs,
        "pid": str(tdir / "dispatcher.pid"),
        "log": str(tdir / "dispatcher.log"),
        "state": str(tdir / "state.json"),
        "panes": [p.pane for p in cfg.task_panes],
    }
    return {
        "session_name": cfg.session_name,
        "windows": [w.window_name for w in cfg.windows],
        "runtime_dir": str(cfg.runtime_dir),
        "runtime_map": str(cfg.runtime_map_path),
        "panes": panes_map,
        "tasks": tasks_info,
    }


def write_runtime_map(cfg: SwarmConfig) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    init_comms_db(cfg.session_name)
    cfg.runtime_map_path.write_text(json.dumps(build_runtime_map(cfg), indent=2) + "\n")


def build_this_text(cfg: SwarmConfig) -> str:
    """Resolved identity for this swarm (config + runtime.json location).

    Machine state stays in runtime.json on disk. Workflow lives in
    `aiswarm instructions`. This is only "which swarm / where is the map".
    """
    map_path = cfg.runtime_map_path
    map_note = "present" if map_path.is_file() else "missing — run aiswarm start"
    panes = " ".join(p.pane for p in cfg.panes) or "(none)"
    return "\n".join(
        [
            f"Session: {cfg.session_name}",
            f"Config:  {cfg.path}",
            f"Runtime: {map_path}  ({map_note})",
            f"Panes:   {panes}",
            "",
            "Runtime JSON is the machine map (targets, sockets, paths).",
            "Workflow: aiswarm instructions overview",
            "",
        ]
    )


# --- Event log comms (source of truth + buffer) ---
# Keyed by tmux pane (e.g. "0.2") within a session. This is the stable identity
# for the tmux swarm (agents can be killed/restarted in the pane).
# Writers (global clock, humans, scripts) use log_send / log_broadcast.
# Consumer reads pending for a pane + its monitor state, then tmux-send when ready.

import sqlite3 as _sqlite3

def _comms_db_path(session_name: str) -> Path:
    return Path("/tmp/nudge-swarm") / session_name / "comms.db"

def init_comms_db(session_name: str) -> Path:
    """Ensure the per-session comms DB and tables exist."""
    db = _comms_db_path(session_name)
    db.parent.mkdir(parents=True, exist_ok=True)
    with _sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                recipient TEXT NOT NULL,
                sender TEXT,
                type TEXT DEFAULT 'msg',
                payload TEXT NOT NULL,
                meta TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cursors (
                recipient TEXT PRIMARY KEY,
                last_id INTEGER NOT NULL DEFAULT 0
            )
        """)
    return db

def log_send(session_name: str, recipient: str, payload: str, sender: str = None,
             etype: str = "msg", meta: dict | None = None) -> int:
    """Append to the event log for a pane recipient. Returns event id."""
    db = init_comms_db(session_name)
    m = json.dumps(meta) if meta else None
    with _sqlite3.connect(str(db)) as conn:
        cur = conn.execute(
            "INSERT INTO events (recipient, sender, type, payload, meta) "
            "VALUES (?,?,?,?,?)",
            (recipient, sender, etype, payload, m)
        )
        eid = cur.lastrowid
    return eid

def log_broadcast(session_name: str, message: str, include_nonmonitored: bool = False,
                  sender: str = None) -> None:
    """Write a broadcast event. Consumer will fan out to appropriate panes."""
    # For simplicity we write a special recipient; real fan-out can happen at consume time
    # or we can enumerate panes here. Start simple.
    log_send(session_name, "__broadcast__", message, sender, "broadcast")


def log_ack(session_name: str, pane: str, acked_event_id: int,
            acked_recipient: str, target: str) -> int:
    return log_send(
        session_name,
        f"{pane}:ack",
        "",
        sender="consumer",
        etype="ack",
        meta={
            "acked_event_id": acked_event_id,
            "acked_recipient": acked_recipient,
            "pane": pane,
            "target": target,
            "delivery": "tmux-send",
        },
    )


def get_pending_events(session_name: str, recipient: str):
    """Return (id, ts, sender, type, payload, meta) for unread events."""
    db = _comms_db_path(session_name)
    if not db.exists():
        return []
    with _sqlite3.connect(str(db)) as conn:
        cur = conn.execute("SELECT last_id FROM cursors WHERE recipient = ?", (recipient,))
        row = cur.fetchone()
        last = row[0] if row else 0
        cur = conn.execute(
            "SELECT id, ts, sender, type, payload, meta FROM events "
            "WHERE recipient = ? AND id > ? ORDER BY id",
            (recipient, last)
        )
        return cur.fetchall()

def advance_cursor(session_name: str, recipient: str, last_id: int):
    """Mark events up to last_id as read for this recipient."""
    db = init_comms_db(session_name)
    with _sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cursors (recipient, last_id) VALUES (?,?)",
            (recipient, last_id)
        )


def get_cursors(session_name: str) -> dict[str, int]:
    """Return {recipient: last_read_id}."""
    db = _comms_db_path(session_name)
    if not db.exists():
        return {}
    with _sqlite3.connect(str(db)) as conn:
        cur = conn.execute("SELECT recipient, last_id FROM cursors ORDER BY recipient")
        return {row[0]: row[1] for row in cur.fetchall()}


def get_events(session_name: str, recipient: str | None = None, limit: int = 100) -> list:
    """Return events in chrono order (oldest first). Optional recipient filter."""
    db = _comms_db_path(session_name)
    if not db.exists():
        return []
    with _sqlite3.connect(str(db)) as conn:
        if recipient is not None:
            sql = (
                "SELECT id, ts, recipient, sender, type, payload, meta FROM events "
                "WHERE recipient IN (?,?) ORDER BY id DESC LIMIT ?"
            )
            params = (recipient, f"{recipient}:ack", limit)
        else:
            sql = (
                "SELECT id, ts, recipient, sender, type, payload, meta FROM events "
                "ORDER BY id DESC LIMIT ?"
            )
            params = (limit,)
        rows = list(conn.execute(sql, params))
        return list(reversed(rows))


def get_pending_count(session_name: str, recipient: str) -> int:
    return len(get_pending_events(session_name, recipient))


def get_pending_broadcasts(session_name: str, pane: str):
    """Pending broadcast events, using a per-pane cursor for __broadcast__ so
    multiple panes don't interfere with each other's broadcast cursors."""
    bcast_key = f"{pane}:bcast"
    db = _comms_db_path(session_name)
    if not db.exists():
        return []
    with _sqlite3.connect(str(db)) as conn:
        cur = conn.execute("SELECT last_id FROM cursors WHERE recipient = ?", (bcast_key,))
        row = cur.fetchone()
        last = row[0] if row else 0
        cur = conn.execute(
            "SELECT id, ts, sender, type, payload, meta FROM events "
            "WHERE recipient = '__broadcast__' AND id > ? ORDER BY id",
            (last,)
        )
        return cur.fetchall()


def advance_broadcast_cursor(session_name: str, pane: str, last_id: int):
    bcast_key = f"{pane}:bcast"
    db = init_comms_db(session_name)
    with _sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cursors (recipient, last_id) VALUES (?,?)",
            (bcast_key, last_id)
        )


def clear_comms(session_name: str, confirm: bool = False):
    """Clear all events and cursors for the session.
    Requires explicit confirm=True (callers must do the 'y' prompt).
    """
    if not confirm:
        print("clear_comms: pass confirm=True after user confirmation")
        return
    db = _comms_db_path(session_name)
    if db.exists():
        with _sqlite3.connect(str(db)) as conn:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM cursors")
        # VACUUM cannot run inside a transaction
        with _sqlite3.connect(str(db)) as conn:
            conn.execute("VACUUM")
        print(f"cleared comms log for {session_name}")


# --- agentsview provider usage (task-7) ---

import datetime as _dt
import os as _os
import subprocess as _subp
from shutil import which as _which


def _agentsview_bin() -> str:
    # Prefer the dev tree build that matches the running server on 8088
    for cand in (
        "/home/cottrell/dev/agentsview/bin/agentsview",
        _os.path.expanduser("~/.local/bin/agentsview"),
    ):
        if _os.path.isfile(cand) and _os.access(cand, _os.X_OK):
            return cand
    w = _which("agentsview")
    return w or "agentsview"


def _model_to_provider(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m:
        return "claude"
    if "gpt" in m or "o1" in m or "o3" in m:
        return "codex"
    if "gemini" in m:
        return "gemini"
    if "grok" in m:
        return "grok"
    if "mistral" in m or "vibe" in m or "devstral" in m:
        return "vibe"
    if "qwen" in m:
        return "qwen"
    if "kimi" in m:
        return "kimi"
    return "other"


def get_agentsview_provider_usage(*, since: str | None = None, until: str | None = None, no_sync: bool = True) -> dict:
    """Return provider-grouped usage from agentsview.

    Uses agentsview usage daily --json (correct pricing from model_pricing).
    "Provider" here means backend family (claude/codex/gemini/...) derived from model.
    """
    binp = _agentsview_bin()
    argv = [binp, "usage", "daily", "--json"]
    if since:
        argv += ["--since", since]
    if until:
        argv += ["--until", until]
    if no_sync:
        argv += ["--no-sync"]
    try:
        proc = _subp.run(argv, check=False, stdout=_subp.PIPE, stderr=_subp.PIPE, text=True, timeout=30)
    except FileNotFoundError:
        return {"error": f"agentsview CLI not found (tried {binp})"}
    if proc.returncode != 0:
        return {"error": (proc.stderr or proc.stdout or "agentsview usage failed").strip()[:300]}
    try:
        data = json.loads(proc.stdout)
    except Exception as e:
        return {"error": f"parse json: {e}"}

    provs: dict[str, dict] = {}
    for day in data.get("daily", []):
        for mb in day.get("modelBreakdowns", []):
            p = _model_to_provider(mb.get("modelName", ""))
            if p not in provs:
                provs[p] = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0, "models": set()}
            provs[p]["cost"] += mb.get("cost") or 0.0
            provs[p]["input_tokens"] += mb.get("inputTokens") or 0
            provs[p]["output_tokens"] += mb.get("outputTokens") or 0
            provs[p]["cache_creation_tokens"] += mb.get("cacheCreationTokens") or 0
            provs[p]["cache_read_tokens"] += mb.get("cacheReadTokens") or 0
            if mb.get("modelName"):
                provs[p]["models"].add(mb["modelName"])
    for p in provs:
        provs[p]["models"] = sorted(provs[p].pop("models"))
    return {
        "date_range": {"from": data.get("from") or since, "to": data.get("to") or until},
        "providers": provs,
        "totals": data.get("totals", {}),
        "raw": {"sessionCounts": data.get("sessionCounts"), "agentTotals": data.get("agentTotals")},
    }


def get_agentsview_today_provider_usage() -> dict:
    today = _dt.date.today().isoformat()
    return get_agentsview_provider_usage(since=today, until=today)


def get_agentsview_recent_tokens(minutes: int = 5, agents: list[str] | None = None) -> dict:
    """Query usage_events directly (single SQL + join) for recent token burn.

    Groups by the (normalized) agent from sessions. Cheap even for small windows.
    """
    db_path = _os.path.expanduser("~/.agentsview/sessions.db")
    if not _os.path.exists(db_path):
        return {"error": f"no sessions.db at {db_path}"}
    try:
        import sqlite3 as _sqlite3
        from datetime import datetime as _dtm, timedelta as _td, timezone as _tz
        cutoff = _dtm.now(_tz.utc) - _td(minutes=minutes)
        normed = None
        if agents:
            normed = {normalize_agentsview_agent(a) for a in agents}

        con = _sqlite3.connect(db_path)
        cur = con.cursor()
        # one query: join to get agent, pull recent window then python filter for tz accuracy
        cur.execute(
            """
            SELECT s.agent, u.model, u.input_tokens, u.output_tokens,
                   u.cache_creation_input_tokens, u.cache_read_input_tokens, u.occurred_at
            FROM usage_events u
            JOIN sessions s ON u.session_id = s.id
            WHERE u.occurred_at >= date('now', '-2 days')
            """
        )
        rows = cur.fetchall()
        con.close()
    except Exception as e:
        return {"error": str(e)[:200]}

    provs: dict[str, dict] = {}
    total_tokens = 0
    kept = 0
    for ag, model, it, ot, cc, cr, ts in rows:
        if normed and ag not in normed:
            continue
        try:
            ts = ts.replace("Z", "+00:00")
            if "+" not in ts and "-" not in ts[10:]:
                tso = _dtm.fromisoformat(ts)
            else:
                tso = _dtm.fromisoformat(ts)
            if tso.tzinfo is None:
                tso = tso.replace(tzinfo=_tz.utc)
            else:
                tso = tso.astimezone(_tz.utc)
            if tso < cutoff:
                continue
        except Exception:
            continue
        kept += 1
        key = ag or _model_to_provider(model)
        if key not in provs:
            provs[key] = {"tokens": 0, "input": 0, "output": 0, "models": set(), "count": 0}
        t = (it or 0) + (ot or 0) + (cc or 0) + (cr or 0)
        provs[key]["tokens"] += t
        provs[key]["input"] += it or 0
        provs[key]["output"] += ot or 0
        provs[key]["count"] += 1
        if model:
            provs[key]["models"].add(model)
        total_tokens += t
    for k in provs:
        provs[k]["models"] = sorted(provs[k].pop("models"))
    return {
        "window_minutes": minutes,
        "providers": provs,
        "total_tokens": total_tokens,
        "events": kept,
    }


# --- config-aware agentsview usage (for av-usage <config>) ---

AGENTSVIEW_AGENT_MAP = {
    "antigravity": "antigravity-cli",
    "agy": "antigravity-cli",
}


def normalize_agentsview_agent(name: str) -> str:
    return AGENTSVIEW_AGENT_MAP.get(name, name)


def _read_agentsview_auth() -> str | None:
    try:
        text = (Path.home() / ".agentsview" / "config.toml").read_text()
        for line in text.splitlines():
            if "auth_token" in line and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    except Exception:
        pass
    return None


def _find_agentsview_port() -> int | None:
    try:
        d = Path.home() / ".agentsview"
        files = sorted(d.glob("server.*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            data = json.loads(files[0].read_text())
            return int(data.get("port") or 0) or None
    except Exception:
        pass
    return None


def get_agentsview_all_agents() -> list[str]:
    """Return the complete list of known agents/providers from agentsview.

    Prefers the /api/v1/agents endpoint (includes all ever seen).
    Falls back to distinct agents from the sessions table in the DB.
    """
    token = _read_agentsview_auth()
    port = _find_agentsview_port()
    if token and port:
        import urllib.request as _url
        base = f"http://bleepblop:{port}"
        try:
            req = _url.Request(f"{base}/api/v1/agents", headers={"Authorization": f"Bearer {token}"})
            with _url.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                names = [a["name"] for a in data.get("agents", []) if a.get("name")]
                return sorted(set(names))
        except Exception:
            pass

    # DB fallback
    try:
        import sqlite3 as _sqlite3
        db_path = _os.path.expanduser("~/.agentsview/sessions.db")
        con = _sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT DISTINCT agent FROM sessions WHERE agent IS NOT NULL ORDER BY agent")
        names = [r[0] for r in cur.fetchall()]
        con.close()
        return names
    except Exception:
        return []


def get_agentsview_usage_summary(
    *, agents: list[str] | None = None, since: str | None = None, until: str | None = None
) -> dict:
    """Efficient query against the running agentsview server (one roundtrip).

    If agents list given, server-side filter (comma joined). Uses the /api/v1/usage/summary
    which returns agentTotals + daily with agentBreakdowns.
    Falls back to CLI if server not reachable.
    """
    token = _read_agentsview_auth()
    port = _find_agentsview_port()
    if not token or not port:
        # fallback to CLI path (may do multiple if per-agent needed)
        joined = ",".join(agents) if agents else None
        return get_agentsview_provider_usage(since=since, until=until)  # best effort, unfiltered for now

    base = f"http://bleepblop:{port}"
    params = {}
    if since:
        params["from"] = since
    if until:
        params["to"] = until
    if agents:
        # use normalized
        normed = [normalize_agentsview_agent(a) for a in agents]
        params["agent"] = ",".join(normed)

    import urllib.request as _url
    import urllib.parse as _parse

    q = _parse.urlencode(params)
    url = f"{base}/api/v1/usage/summary?{q}" if q else f"{base}/api/v1/usage/summary"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        req = _url.Request(url, headers=headers)
        with _url.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception as e:
        # fallback
        return {"error": f"api query failed: {e}", "fallback": True}


def _get_usage_for_agent_via_cli(agent: str, since: str, until: str) -> dict:
    """Call the agentsview binary for a single agent and date range.
    Returns the totals dict for that agent (or zeros if none).
    """
    binp = _agentsview_bin()
    if not binp or binp == "agentsview" and not _os.path.exists("/home/cottrell/dev/agentsview/bin/agentsview"):
        # fallback zeros
        return {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0}

    argv = [binp, "usage", "daily", "--agent", agent, "--json", "--no-sync",
            "--since", since, "--until", until]
    try:
        proc = _subp.run(argv, check=False, stdout=_subp.PIPE, stderr=_subp.PIPE, text=True, timeout=15)
        if proc.returncode != 0:
            return {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0}
        data = json.loads(proc.stdout)
        # When filtered to one agent, the top-level totals are for it.
        # Also check sessionCounts.byAgent to confirm.
        totals = data.get("totals", {})
        return {
            "cost": float(totals.get("totalCost") or 0),
            "input_tokens": int(totals.get("inputTokens") or 0),
            "output_tokens": int(totals.get("outputTokens") or 0),
            "cache_creation_tokens": int(totals.get("cacheCreationTokens") or 0),
            "cache_read_tokens": int(totals.get("cacheReadTokens") or 0),
        }
    except Exception:
        return {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0}


def get_swarm_agentsview_report(agents: list[str] | None = None) -> dict:
    """Return convenient report using global agentsview usage data.

    If agents list is provided, limits to (normalized) those agents.
    If None/empty, shows *all* known agents from agentsview (full global list),
    with usage overlaid (0 for agents with no spend in the window).
    Uses the agentsview CLI binary per-agent for accuracy (the HTTP summary
    sometimes misses data for agents like antigravity-cli).
    """
    today = _dt.date.today().isoformat()
    week_ago = (_dt.date.today() - _dt.timedelta(days=6)).isoformat()

    if agents:
        norm_agents = sorted({normalize_agentsview_agent(a) for a in agents})
        display_agents = norm_agents
    else:
        display_agents = get_agentsview_all_agents()

    # Build per-agent data using CLI (more reliable than current HTTP summary for some agents)
    today_by = {}
    week_by = {}
    for ag in display_agents:
        today_by[ag] = _get_usage_for_agent_via_cli(ag, today, today)
        week_by[ag] = _get_usage_for_agent_via_cli(ag, week_ago, today)

    # Compute group totals (sum of what we have)
    def sum_by(d):
        return {
            "inputTokens": sum(x["input_tokens"] for x in d.values()),
            "outputTokens": sum(x["output_tokens"] for x in d.values()),
            "cacheCreationTokens": sum(x["cache_creation_tokens"] for x in d.values()),
            "cacheReadTokens": sum(x["cache_read_tokens"] for x in d.values()),
            "totalCost": sum(x["cost"] for x in d.values()),
        }

    return {
        "agents": display_agents,
        "today": {
            "date": today,
            "by_agent": today_by,
            "totals": sum_by(today_by),
        },
        "week": {
            "from": week_ago,
            "to": today,
            "by_agent": week_by,
            "totals": sum_by(week_by),
        },
        "recent": get_agentsview_recent_tokens(10, agents=display_agents),
    }


def get_agents_from_config(cfg: SwarmConfig) -> list[str]:
    return sorted({p.agent for p in cfg.panes if p.agent})


QUOTA_AGENT_MAP = {"antigravity": "agy"}


# --- global agent provider quota caching ---

def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


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

    # Just a time: "3:39pm" or "15:39" or "03:39 am"
    m = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)?$', s, re.IGNORECASE)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = (m.group(3) or '').lower()
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt.timestamp() <= now.timestamp():
            dt += timedelta(days=1)
        return int(dt.timestamp())

    # relative duration: "24h 44m" or "2h 14m" or "in 2h 14m"
    m = re.search(r'(?:in\s+)?(?:(\d+)h)?\s*(?:(\d+)m)?', s, re.IGNORECASE)
    if m and (m.group(1) or m.group(2)):
        h = int(m.group(1) or 0)
        m_val = int(m.group(2) or 0)
        return int((now + timedelta(hours=h, minutes=m_val)).timestamp())

    return None


def _ts_to_iso(ts: int | None) -> str:
    """Convert a Unix timestamp integer to an ISO 8601 string in local timezone."""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).isoformat()
    except Exception:
        return ""


def parse_claude_usage(text: str) -> dict:
    """Parse raw Claude Code /usage text into a structured dictionary."""
    res = {
        "cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "limits": []
    }
    cost_m = re.search(r'Total cost:\s+\$(\d+\.\d+)', text)
    if cost_m:
        res["cost"] = float(cost_m.group(1))

    usage_m = re.search(
        r'Usage:\s+(\d+)\s+input,\s+(\d+)\s+output,\s+(\d+)\s+cache\s+read,\s+(\d+)\s+cache\s+write',
        text,
        re.IGNORECASE
    )
    if usage_m:
        res["input_tokens"] = int(usage_m.group(1))
        res["output_tokens"] = int(usage_m.group(2))
        res["cache_read_tokens"] = int(usage_m.group(3))
        res["cache_write_tokens"] = int(usage_m.group(4))

    session_block = re.search(
        r'Current session(.*?)(?:Current week|approximate|What\'s contributing|$)',
        text,
        re.DOTALL | re.IGNORECASE
    )
    if session_block:
        block_text = session_block.group(1)
        pct_m = re.search(r'(\d+)%\s+used', block_text, re.IGNORECASE)
        reset_m = re.search(r'Resets\s+(.+)', block_text, re.IGNORECASE)
        if pct_m and reset_m:
            pct_used = int(pct_m.group(1))
            reset = reset_m.group(1).strip()
            reset_ts = _parse_reset_ts(reset) or 0
            res["limits"].append({
                "label": "session",
                "pct": max(0, 100 - pct_used),
                "reset": reset,
                "reset_ts": reset_ts,
                "reset_iso": _ts_to_iso(reset_ts)
            })

    week_block = re.search(
        r'Current week(.*?)(?:approximate|What\'s contributing|Session|$)',
        text,
        re.DOTALL | re.IGNORECASE
    )
    if week_block:
        block_text = week_block.group(1)
        pct_m = re.search(r'(\d+)%\s+used', block_text, re.IGNORECASE)
        reset_m = re.search(r'Resets\s+(.+)', block_text, re.IGNORECASE)
        if pct_m and reset_m:
            pct_used = int(pct_m.group(1))
            reset = reset_m.group(1).strip()
            reset_ts = _parse_reset_ts(reset) or 0
            res["limits"].append({
                "label": "weekly",
                "pct": max(0, 100 - pct_used),
                "reset": reset,
                "reset_ts": reset_ts,
                "reset_iso": _ts_to_iso(reset_ts)
            })
    return res


def parse_codex_usage(text: str) -> dict:
    """Parse raw OpenAI Codex /status text into a structured dictionary."""
    res = {
        "model": "",
        "account": "",
        "session_id": "",
        "limits": []
    }
    for line in text.splitlines():
        if "Model:" in line:
            res["model"] = line.split("Model:", 1)[1].strip().rstrip('│').strip()
        elif "Account:" in line:
            res["account"] = line.split("Account:", 1)[1].strip().rstrip('│').strip()
        elif "Session:" in line:
            res["session_id"] = line.split("Session:", 1)[1].strip().rstrip('│').strip()

    for line in text.splitlines():
        lim_m = re.search(
            r'(\w+)\s+limit:\s*(?:\[[^\]]*\])?\s*(\d+)%\s+left\s*\((?:resets\s+)?([^\)]+)\)',
            line,
            re.IGNORECASE
        )
        if lim_m:
            label = lim_m.group(1).lower()
            pct = int(lim_m.group(2))
            reset = lim_m.group(3).strip()
            reset_ts = _parse_reset_ts(reset) or 0
            res["limits"].append({
                "label": label,
                "pct": pct,
                "reset": reset,
                "reset_ts": reset_ts,
                "reset_iso": _ts_to_iso(reset_ts)
            })
    return res


def parse_agy_usage(text: str) -> dict:
    """Parse raw Antigravity /usage text into a structured dictionary."""
    res = {
        "groups": [],
        "limits": []
    }
    blocks = re.split(r'([^\S\r\n]*[A-Z0-9_\- \t]+MODELS)\s*\n', text, flags=re.IGNORECASE)
    if len(blocks) > 1:
        for idx in range(1, len(blocks), 2):
            group_name = blocks[idx].strip()
            block_content = blocks[idx+1]
            
            group_entry = {
                "group": group_name,
                "models": [],
                "limits": []
            }
            
            models_m = re.search(r'Models within this group:\s*(.+)', block_content, re.IGNORECASE)
            if models_m:
                group_entry["models"] = [m.strip() for m in models_m.group(1).split(",")]
                
            limit_blocks = re.split(
                r'^[^\S\r\n]*([a-zA-Z0-9_\-]+(?:[^\S\r\n]+[a-zA-Z0-9_\-]+){0,2}\s+Limit)\s*\n',
                block_content,
                flags=re.MULTILINE | re.IGNORECASE
            )
            if len(limit_blocks) > 1:
                for l_idx in range(1, len(limit_blocks), 2):
                    limit_label = limit_blocks[l_idx].strip().lower().replace(" limit", "")
                    limit_content = limit_blocks[l_idx+1]

                    pct_remaining = 0
                    reset = ""

                    # Check for "N% remaining · Refreshes in X" (explicit remaining)
                    rem_m = re.search(r'(\d+(?:\.\d+)?)%\s+remaining\s+·\s+Refreshes\s+in\s+(.+)', limit_content, re.IGNORECASE)
                    if rem_m:
                        pct_remaining = int(float(rem_m.group(1)))
                        reset = "in " + rem_m.group(2).strip()
                    elif "quota available" in limit_content.lower():
                        # "Quota available" with 100% shown means exhausted (0% remaining)
                        pct_remaining = 0
                        reset = "Exhausted"
                    else:
                        # Fallback: extract percentage (used) and invert to get remaining
                        pct_m = re.search(r'(\d+(?:\.\d+)?)%', limit_content)
                        if pct_m:
                            pct_used = int(float(pct_m.group(1)))
                            pct_remaining = 100 - pct_used

                    reset_ts = _parse_reset_ts(reset) or 0
                    group_entry["limits"].append({
                        "label": limit_label,
                        "pct": pct_remaining,
                        "reset": reset,
                        "reset_ts": reset_ts,
                        "reset_iso": _ts_to_iso(reset_ts)
                    })
            res["groups"].append(group_entry)
            
    for g in res["groups"]:
        prefix = "gemini" if "gemini" in g["group"].lower() else "claude_gpt"
        for lim in g["limits"]:
            res["limits"].append({
                "label": f"{prefix}_{lim['label']}",
                "pct": lim["pct"],
                "reset": lim["reset"],
                "reset_ts": lim["reset_ts"],
                "reset_iso": lim["reset_iso"]
            })
    return res


def parse_provider_usage(agent: str, text: str) -> dict:
    """Parse raw usage text into a structured dictionary specific to the agent."""
    if agent == "claude":
        return parse_claude_usage(text)
    elif agent == "codex":
        return parse_codex_usage(text)
    elif agent == "agy":
        return parse_agy_usage(text)
    return {"limits": []}


def get_cached_provider_usage(agent: str, ttl: int = 120, force: bool = False) -> dict:
    """Get provider usage with TTL caching, calling the underlying shell script if needed.
    
    Persisted cache: /tmp/nudge-usage-cache.json
    """
    cache_file = Path("/tmp/nudge-usage-cache.json")
    cache: dict = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except Exception:
            cache = {}
            
    now_ts = int(time.time())
    entry = cache.get(agent)
    
    # Check if we can reuse the cached raw text
    use_cache = False
    if entry and not force:
        fetched_at = entry.get("fetched_at", 0)
        if now_ts - fetched_at < ttl:
            use_cache = True

    if use_cache:
        raw_text = entry.get("raw_text", "")
        parsed = parse_provider_usage(agent, raw_text)
        return {
            "raw_text": raw_text,
            "parsed": parsed,
            "limits": parsed.get("limits", []),
            "fetched_at": fetched_at,
            "fetched_at_iso": entry.get("fetched_at_iso", _ts_to_iso(fetched_at))
        }

    # Otherwise, run the scraper script
    script_path = ROOT_DIR / "swarm" / "usage" / f"{agent}.sh"
    if not script_path.exists():
        if entry:
            raw_text = entry.get("raw_text", "")
            parsed = parse_provider_usage(agent, raw_text)
            return {
                "error": f"Script not found at {script_path}",
                "raw_text": raw_text,
                "parsed": parsed,
                "limits": parsed.get("limits", []),
                "fetched_at": entry.get("fetched_at", 0),
                "fetched_at_iso": entry.get("fetched_at_iso", "")
            }
        return {"error": f"Script not found at {script_path}", "limits": [], "fetched_at": now_ts}

    try:
        proc = subprocess.run(
            [str(script_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
    except subprocess.TimeoutExpired:
        if entry:
            raw_text = entry.get("raw_text", "")
            parsed = parse_provider_usage(agent, raw_text)
            return {
                "warning": "Scraper timeout; returned stale cached data",
                "raw_text": raw_text,
                "parsed": parsed,
                "limits": parsed.get("limits", []),
                "fetched_at": entry.get("fetched_at", 0),
                "fetched_at_iso": entry.get("fetched_at_iso", "")
            }
        return {"error": "Scraper script timed out", "limits": [], "fetched_at": now_ts}
    except Exception as e:
        if entry:
            raw_text = entry.get("raw_text", "")
            parsed = parse_provider_usage(agent, raw_text)
            return {
                "warning": f"Scraper error: {e}; returned stale cached data",
                "raw_text": raw_text,
                "parsed": parsed,
                "limits": parsed.get("limits", []),
                "fetched_at": entry.get("fetched_at", 0),
                "fetched_at_iso": entry.get("fetched_at_iso", "")
            }
        return {"error": f"Scraper failed to run: {e}", "limits": [], "fetched_at": now_ts}

    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip()
        if entry:
            raw_text = entry.get("raw_text", "")
            parsed = parse_provider_usage(agent, raw_text)
            return {
                "warning": f"Scraper exit {proc.returncode}: {err_msg}; returned stale cached data",
                "raw_text": raw_text,
                "parsed": parsed,
                "limits": parsed.get("limits", []),
                "fetched_at": entry.get("fetched_at", 0),
                "fetched_at_iso": entry.get("fetched_at_iso", "")
            }
        return {"error": f"Scraper exit {proc.returncode}: {err_msg}", "limits": [], "fetched_at": now_ts}

    raw_output = proc.stdout or ""
    clean_text = strip_ansi(raw_output)

    new_entry = {
        "raw_text": clean_text,
        "fetched_at": now_ts,
        "fetched_at_iso": datetime.fromtimestamp(now_ts).isoformat()
    }
    
    # Update cache atomically
    cache[agent] = new_entry
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=str(cache_file.parent), delete=False) as tf:
            json.dump(cache, tf, indent=2)
            temp_name = tf.name
        os.replace(temp_name, str(cache_file))
    except Exception as e:
        new_entry["warning"] = f"Failed to write cache: {e}"

    # Parse on-the-fly for the return value
    parsed = parse_provider_usage(agent, clean_text)
    return {
        **new_entry,
        "parsed": parsed,
        "limits": parsed.get("limits", [])
    }
