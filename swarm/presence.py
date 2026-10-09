#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

GLOBAL_PRESENCE_PATH = Path("/tmp/nudge-swarm/presence_global.json")
DEFAULT_IDLE_TIMEOUT_SECS = 900  # 15 minutes


def local_presence_path(session_name: str) -> Path:
    return Path("/tmp/nudge-swarm") / session_name / "presence_local.json"


@dataclass
class TmuxClientInfo:
    session: str
    last_activity: int


def get_tmux_clients() -> list[TmuxClientInfo]:
    """Inspect attached tmux clients via tmux list-clients."""
    try:
        res = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_session} #{client_activity}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return []
        clients: list[TmuxClientInfo] = []
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                session = parts[0]
                try:
                    activity = int(parts[1])
                    clients.append(TmuxClientInfo(session=session, last_activity=activity))
                except ValueError:
                    continue
        return clients
    except Exception:
        return []


def load_override(path: Path) -> tuple[str | None, float | None]:
    """Read state override and expiration from a JSON file.
    Returns (mode, until). If expired, returns (None, None) and unlinks file.
    """
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text())
        mode = data.get("mode")
        until = data.get("until")
        if until is not None and time.time() >= float(until):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None, None
        return mode, until
    except Exception:
        return None, None


def save_override(path: Path, mode: str, until: float | None = None) -> None:
    """Save state override to JSON file. If mode is None, 'global', 'clear', or resetting global to 'auto', removes file."""
    if mode in (None, "global", "clear"):
        path.unlink(missing_ok=True)
        return
    if mode == "auto" and path.name == "presence_global.json":
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    data: dict[str, Any] = {"mode": mode}
    if until is not None:
        data["until"] = until
    tmp_path.write_text(json.dumps(data) + "\n")
    tmp_path.replace(path)


def format_idle(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem_s = seconds % 60
    if minutes < 60:
        return f"{minutes}m {rem_s}s" if rem_s > 0 else f"{minutes}m"
    hours = minutes // 60
    rem_m = minutes % 60
    return f"{hours}h {rem_m}m" if rem_m > 0 else f"{hours}h"


@dataclass
class ScopeEvaluation:
    state: str  # "in" or "out"
    source: str  # e.g. "pinned: in", "auto (idle 42s across 2 clients)"
    mode: str  # configured mode: "auto", "in", "out", "global"
    idle_seconds: int | None = None
    client_count: int = 0
    until: float | None = None


@dataclass
class PresenceStatus:
    effective: str  # "in" or "out"
    local: ScopeEvaluation
    global_eval: ScopeEvaluation
    session_name: str | None = None

    def summary(self) -> str:
        lines = []
        lines.append(f"Effective: {self.effective.upper()}")
        if self.session_name:
            lines.append(f"  Local ({self.session_name}): {self.local.source}")
        else:
            lines.append(f"  Local: {self.local.source}")
        lines.append(f"  Global: {self.global_eval.source}")
        return "\n".join(lines)


def evaluate_presence(
    session_name: str | None = None,
    idle_timeout: int = DEFAULT_IDLE_TIMEOUT_SECS,
    clients: list[TmuxClientInfo] | None = None,
    now: float | None = None,
    global_path: Path = GLOBAL_PRESENCE_PATH,
    local_path: Path | None = None,
) -> PresenceStatus:
    if now is None:
        now = time.time()
    if clients is None:
        clients = get_tmux_clients()

    # 1. Global evaluation
    g_mode, g_until = load_override(global_path)
    if g_mode in ("in", "out"):
        g_until_str = f" until {time.strftime('%H:%M:%S', time.localtime(g_until))}" if g_until else ""
        g_eval = ScopeEvaluation(
            state=g_mode,
            source=f"pinned: {g_mode}{g_until_str}",
            mode=g_mode,
            until=g_until,
        )
    else:
        # Global auto: passive detection across ALL attached clients
        g_count = len(clients)
        if g_count == 0:
            g_eval = ScopeEvaluation(
                state="out",
                source="auto (no tmux clients attached)",
                mode="auto",
                idle_seconds=None,
                client_count=0,
            )
        else:
            latest = max(c.last_activity for c in clients)
            idle = max(0, int(now - latest))
            state = "in" if idle < idle_timeout else "out"
            g_eval = ScopeEvaluation(
                state=state,
                source=f"auto ({state.upper()}, idle {format_idle(idle)}, {g_count} client{'s' if g_count > 1 else ''})",
                mode="auto",
                idle_seconds=idle,
                client_count=g_count,
            )

    # 2. Local evaluation
    if local_path is None and session_name:
        local_path = local_presence_path(session_name)

    l_mode, l_until = load_override(local_path) if local_path else (None, None)
    if l_mode in ("in", "out"):
        l_until_str = f" until {time.strftime('%H:%M:%S', time.localtime(l_until))}" if l_until else ""
        l_eval = ScopeEvaluation(
            state=l_mode,
            source=f"pinned: {l_mode}{l_until_str}",
            mode=l_mode,
            until=l_until,
        )
        effective = l_mode
    elif l_mode == "auto" and session_name:
        # Local auto: scoped strictly to clients viewing THIS swarm session
        session_clients = [c for c in clients if c.session == session_name]
        s_count = len(session_clients)
        if s_count == 0:
            l_eval = ScopeEvaluation(
                state="out",
                source=f"auto (no clients attached to session '{session_name}')",
                mode="auto",
                idle_seconds=None,
                client_count=0,
            )
            effective = "out"
        else:
            latest = max(c.last_activity for c in session_clients)
            idle = max(0, int(now - latest))
            state = "in" if idle < idle_timeout else "out"
            l_eval = ScopeEvaluation(
                state=state,
                source=f"auto ({state.upper()}, idle {format_idle(idle)}, {s_count} client{'s' if s_count > 1 else ''})",
                mode="auto",
                idle_seconds=idle,
                client_count=s_count,
            )
            effective = state
    else:
        # Default local mode: "global" (follow global)
        l_eval = ScopeEvaluation(
            state=g_eval.state,
            source=f"global (following global -> {g_eval.state.upper()})",
            mode="global",
        )
        effective = g_eval.state

    return PresenceStatus(
        effective=effective,
        local=l_eval,
        global_eval=g_eval,
        session_name=session_name,
    )
