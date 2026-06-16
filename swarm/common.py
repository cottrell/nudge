#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
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


@dataclass
class BabysitSpec:
    enabled: bool
    interval_secs: int = 600
    clear_every: int = 0
    long_prompt: str = ""
    long_prompt_file: Path | None = None
    short_prompt: str = ""
    short_prompt_file: Path | None = None


@dataclass
class PaneSpec:
    pane: str        # "W.N" — window index . pane index within window
    agent: str | None
    command: str
    title: str
    monitor: bool
    babysit: BabysitSpec

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
    def self_awareness_path(self) -> Path:
        return self.runtime_dir / "self-awareness.txt"


def _parse_babysit(raw: dict, pane_id: str, cfg_path: Path) -> BabysitSpec:
    long_prompt_file = raw.get("long_prompt_file") or raw.get("prompt_file")
    short_prompt_file = raw.get("short_prompt_file")
    long_prompt = str(raw.get("long_prompt") or raw.get("prompt") or "")
    short_prompt = str(raw.get("short_prompt") or "")
    long_prompt_path = None
    short_prompt_path = None
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
        enabled=bool(raw.get("enabled", False)),
        interval_secs=int(raw.get("interval_secs", 600)),
        clear_every=int(raw.get("clear_every", 0)),
        long_prompt=long_prompt,
        long_prompt_file=long_prompt_path,
        short_prompt=short_prompt,
        short_prompt_file=short_prompt_path,
    )


def load_config(path: str | Path) -> SwarmConfig:
    cfg_path = Path(path).resolve()
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

        panes: list[PaneSpec] = []
        for pane_idx, praw in enumerate(wraw.get("panes") or []):
            pane_id = f"{win_idx}.{pane_idx}"
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

            babysit_raw = nudge.get("babysit") or {}
            if bool(babysit_raw.get("enabled", False)) and not monitor:
                raise ValueError(f"pane {pane_id} cannot enable babysit when monitor=false")

            panes.append(PaneSpec(
                pane=pane_id,
                agent=agent,
                command=command,
                title=title,
                monitor=monitor,
                babysit=_parse_babysit(babysit_raw, pane_id, cfg_path),
            ))

        windows.append(WindowSpec(window_name=window_name, layout=layout, panes=panes))

    return SwarmConfig(path=cfg_path, session_name=session_name, windows=windows)


def monitor_socket_path(session_name: str, pane: str) -> Path:
    return Path(f"/tmp/{session_name}_{pane}.sock")


def babysit_runtime_paths(cfg: SwarmConfig, pane: str) -> dict[str, str]:
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
            entry["babysit"] = {
                **babysit_runtime_paths(cfg, pane.pane),
                "has_long_prompt": bool(pane.babysit.long_prompt),
                "has_short_prompt": bool(pane.babysit.short_prompt),
            }
        panes_map[pane.pane] = entry
    return {
        "session_name": cfg.session_name,
        "windows": [w.window_name for w in cfg.windows],
        "runtime_dir": str(cfg.runtime_dir),
        "runtime_map": str(cfg.runtime_map_path),
        "panes": panes_map,
    }


def write_runtime_map(cfg: SwarmConfig) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    cfg.runtime_map_path.write_text(json.dumps(build_runtime_map(cfg), indent=2) + "\n")


def build_self_awareness_text(cfg: SwarmConfig) -> str:
    config_path = str(cfg.path)
    lines = [
        f"Swarm session: {cfg.session_name}",
        f"Windows: {', '.join(w.window_name for w in cfg.windows)}",
        f"Runtime map: {cfg.runtime_map_path}",
        f"Status: python {SWARM_CLI} status {config_path} --brief",
        f"Watch: python {SWARM_CLI} status {config_path} --brief -w",
        "",
        "If you need to coordinate with other panes, inspect the runtime map for:",
        "- tmux pane targets",
        "- monitor socket paths",
        "- babysit pid/log/spec paths",
        "",
        "When messaging another pane, ALWAYS use tmux-send:",
        f"- {ROOT_DIR / 'tmux-send'} <target> \"message\"",
        "",
        "Do NOT use raw tmux send-keys to message agents. Raw send-keys often fails",
        "to submit Enter reliably, leaving prompts sitting unexecuted until another",
        "nudge or manual Enter.",
    ]
    return "\n".join(lines) + "\n"


def write_self_awareness_text(cfg: SwarmConfig) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    cfg.self_awareness_path.write_text(build_self_awareness_text(cfg))
