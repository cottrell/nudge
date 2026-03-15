#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
VALID_AGENTS = ("claude", "codex", "copilot", "gemini", "vibe", "qwen")
SHELL_NAMES = {"bash", "sh", "zsh", "fish"}
PANE_RE = re.compile(r"^0\.(\d+)$")


@dataclass
class BabysitSpec:
    enabled: bool
    interval_secs: int = 600
    long_prompt: str = ""
    long_prompt_file: Path | None = None
    short_prompt: str = ""
    short_prompt_file: Path | None = None


@dataclass
class PaneSpec:
    pane: str
    agent: str | None
    command: str
    title: str
    monitor: bool
    babysit: BabysitSpec

    @property
    def pane_index(self) -> int:
        return int(PANE_RE.match(self.pane).group(1))

    def target(self, session_name: str) -> str:
        return f"{session_name}:{self.pane}"


@dataclass
class SwarmConfig:
    path: Path
    session_name: str
    window_name: str
    layout_type: str
    rows: int
    cols: int
    panes: list[PaneSpec]

    @property
    def pane_count(self) -> int:
        return self.rows * self.cols

    @property
    def runtime_dir(self) -> Path:
        return Path("/tmp/nudge-swarm") / self.session_name

    @property
    def runtime_map_path(self) -> Path:
        return self.runtime_dir / "runtime.json"


def load_config(path: str | Path) -> SwarmConfig:
    cfg_path = Path(path).resolve()
    data = yaml.safe_load(cfg_path.read_text()) or {}

    session = data.get("session") or {}
    layout = data.get("layout") or {}
    panes_data = data.get("panes") or []

    name = str(session.get("name") or "").strip()
    if not name:
        raise ValueError("session.name is required")
    if ":" in name:
        raise ValueError("session.name must not contain ':'")

    window = str(session.get("window") or "grid").strip()
    layout_type = str(layout.get("type") or "grid").strip()
    rows = int(layout.get("rows") or 0)
    cols = int(layout.get("cols") or 0)

    if layout_type != "grid":
        raise ValueError(f"unsupported layout.type: {layout_type}")
    if rows <= 0 or cols <= 0:
        raise ValueError("layout.rows and layout.cols must be positive integers")
    if len(panes_data) != rows * cols:
        raise ValueError(f"layout expects {rows * cols} panes but config defines {len(panes_data)}")

    panes: list[PaneSpec] = []
    seen: set[str] = set()
    for raw in panes_data:
        pane_name = str(raw.get("pane") or "").strip()
        match = PANE_RE.match(pane_name)
        if not match:
            raise ValueError(f"pane must look like '0.N': {pane_name!r}")
        if pane_name in seen:
            raise ValueError(f"duplicate pane entry: {pane_name}")
        seen.add(pane_name)

        monitor = bool(raw.get("monitor", True))
        agent = str(raw.get("agent") or "").strip()
        if monitor:
            if not agent:
                raise ValueError(f"pane {pane_name} requires agent when monitor=true")
            if agent not in VALID_AGENTS:
                raise ValueError(f"unknown agent in config: {agent}")
        elif agent and agent not in VALID_AGENTS:
            raise ValueError(f"unknown agent in config: {agent}")

        command = str(raw.get("command") or "").strip()
        if not command:
            raise ValueError(f"pane {pane_name} is missing command")
        title = str(raw.get("title") or agent or pane_name).strip()
        if not title:
            raise ValueError(f"pane {pane_name} needs a non-empty title")

        babysit_raw = raw.get("babysit") or {}
        long_prompt_file = babysit_raw.get("long_prompt_file") or babysit_raw.get("prompt_file")
        short_prompt_file = babysit_raw.get("short_prompt_file")
        long_prompt = str(babysit_raw.get("long_prompt") or babysit_raw.get("prompt") or "")
        short_prompt = str(babysit_raw.get("short_prompt") or "")
        long_prompt_path = None
        short_prompt_path = None
        if long_prompt_file:
            long_prompt_path = (cfg_path.parent / str(long_prompt_file)).resolve()
            if not long_prompt_path.exists():
                raise ValueError(f"pane {pane_name} long_prompt_file not found: {long_prompt_file}")
            if not long_prompt:
                long_prompt = long_prompt_path.read_text()
        if short_prompt_file:
            short_prompt_path = (cfg_path.parent / str(short_prompt_file)).resolve()
            if not short_prompt_path.exists():
                raise ValueError(f"pane {pane_name} short_prompt_file not found: {short_prompt_file}")
            if not short_prompt:
                short_prompt = short_prompt_path.read_text()
        if not short_prompt:
            short_prompt = long_prompt
        if bool(babysit_raw.get("enabled", False)) and not monitor:
            raise ValueError(f"pane {pane_name} cannot enable babysit when monitor=false")

        panes.append(PaneSpec(
            pane=pane_name,
            agent=agent or None,
            command=command,
            title=title,
            monitor=monitor,
            babysit=BabysitSpec(
                enabled=bool(babysit_raw.get("enabled", False)),
                interval_secs=int(babysit_raw.get("interval_secs", 600)),
                long_prompt=long_prompt,
                long_prompt_file=long_prompt_path,
                short_prompt=short_prompt,
                short_prompt_file=short_prompt_path,
            ),
        ))

    pane_indices = sorted(p.pane_index for p in panes)
    expected = list(range(rows * cols))
    if pane_indices != expected:
        raise ValueError(f"pane indices must be contiguous 0..{rows * cols - 1}: got {pane_indices}")

    panes.sort(key=lambda p: p.pane_index)
    return SwarmConfig(
        path=cfg_path,
        session_name=name,
        window_name=window,
        layout_type=layout_type,
        rows=rows,
        cols=cols,
        panes=panes,
    )


def monitor_socket_path(session_name: str, pane: str) -> Path:
    return Path(f"/tmp/{session_name}_{pane}.sock")


def babysit_runtime_paths(cfg: SwarmConfig, pane: str) -> dict[str, str]:
    stem = f"babysit-{pane.replace('.', '-')}"
    return {
        "pid": str(cfg.runtime_dir / f"{stem}.pid"),
        "log": str(cfg.runtime_dir / f"{stem}.log"),
        "spec": str(cfg.runtime_dir / f"{stem}.json"),
    }


def build_runtime_map(cfg: SwarmConfig) -> dict:
    panes: dict[str, dict[str, object]] = {}
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
        panes[pane.pane] = entry
    return {
        "session_name": cfg.session_name,
        "window_name": cfg.window_name,
        "runtime_dir": str(cfg.runtime_dir),
        "runtime_map": str(cfg.runtime_map_path),
        "panes": panes,
    }


def write_runtime_map(cfg: SwarmConfig) -> None:
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    cfg.runtime_map_path.write_text(json.dumps(build_runtime_map(cfg), indent=2) + "\n")
