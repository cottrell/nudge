#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
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
    prompt: str = ""
    prompt_file: Path | None = None


@dataclass
class PaneSpec:
    pane: str
    agent: str
    command: str
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

        agent = str(raw.get("agent") or "").strip()
        if agent not in VALID_AGENTS:
            raise ValueError(f"unknown agent in config: {agent}")

        command = str(raw.get("command") or "").strip()
        if not command:
            raise ValueError(f"pane {pane_name} is missing command")

        babysit_raw = raw.get("babysit") or {}
        prompt_file = babysit_raw.get("prompt_file")
        prompt = str(babysit_raw.get("prompt") or "")
        prompt_path = None
        if prompt_file:
            prompt_path = (cfg_path.parent / str(prompt_file)).resolve()
            if not prompt_path.exists():
                raise ValueError(f"pane {pane_name} prompt_file not found: {prompt_file}")
            if not prompt:
                prompt = prompt_path.read_text()

        panes.append(PaneSpec(
            pane=pane_name,
            agent=agent,
            command=command,
            monitor=bool(raw.get("monitor", True)),
            babysit=BabysitSpec(
                enabled=bool(babysit_raw.get("enabled", False)),
                interval_secs=int(babysit_raw.get("interval_secs", 600)),
                prompt=prompt,
                prompt_file=prompt_path,
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
