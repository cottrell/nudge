#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

from common import ROOT_DIR


def agent_block(name: str) -> str:
    runtime_dir = Path("/tmp/nudge-swarm") / name
    return f"""## Swarm

Swarm workflow: read first:
- Runtime map: `{runtime_dir / "runtime.json"}`
- Self-awareness note: `{runtime_dir / "self-awareness.txt"}`

Use as source of truth for:
- tmux pane targets
- monitor sockets, live state
- babysit pid/log/spec/state files

Messaging another tmux pane: ALWAYS use `tmux-send`.
Do NOT use raw `tmux send-keys ... Enter`.

Required form:
- `{ROOT_DIR / "tmux-send"} <target> "message"`

Reason:
- raw `tmux send-keys ... Enter` often fails to submit Enter
- prompts can sit unexecuted until next nudge or manual Enter

Swarm scripts: `{ROOT_DIR / "swarm"}`.
"""


DEFAULT_AGENTS = ["codex", "claude", "gemini"]

AGENT_COMMANDS: dict[str, str] = {
    "claude": "claude --dangerously-skip-permissions",
    "codex": "codex --dangerously-bypass-approvals-and-sandbox",
    "gemini": "gemini -y",
    "copilot": "copilot --allow-all-tools",
    "vibe": "vibe --agent auto-approve",
}


def _grid_dims(n: int) -> tuple[int, int]:
    """Return (rows, cols) with rows*cols==n, as square as possible."""
    rows = math.isqrt(n)
    while rows > 1 and n % rows != 0:
        rows -= 1
    return rows, n // rows


def _pane_entry(row: int, agent: str) -> str:
    cmd = AGENT_COMMANDS.get(agent, agent)
    return f"""  - pane: "0.{row}"
    title: {agent}
    agent: {agent}
    command: "{cmd}"
    monitor: true
    babysit:
      enabled: false
      interval_secs: 600
      long_prompt_file: "prompts/worker_long.md"
      short_prompt_file: "prompts/worker_short.txt"
"""


def config_text(name: str, agents: list[str] | None = None) -> str:
    if agents is None:
        agents = DEFAULT_AGENTS
    rows, cols = _grid_dims(len(agents))
    panes_block = "".join(_pane_entry(i, a) for i, a in enumerate(agents))
    return f"""session:
  name: {name}
  window: grid

layout:
  type: grid
  rows: {rows}
  cols: {cols}

panes:
{panes_block}"""


def init(name: str, root: str | Path = ".", dry_run: bool = False, agents: list[str] | None = None) -> None:
    root_path = Path(root).resolve()
    swarm_dir = root_path / "swarm"
    prompts_dir = swarm_dir / "prompts"
    config_path = swarm_dir / f"{name}.yaml"
    agents_path = root_path / "AGENTS.md"

    files = {
        config_path: config_text(name, agents),
        prompts_dir / "worker_long.md": "Continue the assigned work. Read AGENTS.md and follow the project workflow.\n",
        prompts_dir / "worker_short.txt": "Continue. Stay in role and keep the current thread moving.\n",
    }

    for path, content in files.items():
        if path.exists():
            print(f"exists: {path}")
            continue
        if dry_run:
            print(f"would create: {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"created: {path}")

    block = agent_block(name)
    if agents_path.exists() and "## Swarm" in agents_path.read_text():
        print(f"AGENTS.md already has ## Swarm: {agents_path}")
    elif dry_run:
        action = "append to" if agents_path.exists() else "create"
        print(f"would {action}: {agents_path}")
        print()
        print(block.rstrip())
    else:
        prefix = ""
        if agents_path.exists() and agents_path.read_text().strip():
            prefix = "\n\n"
        agents_path.parent.mkdir(parents=True, exist_ok=True)
        with agents_path.open("a") as f:
            f.write(prefix + block)
        print(f"updated: {agents_path}")

    print()
    print("Next:")
    print(f"  python {ROOT_DIR / 'swarm' / 'cli.py'} apply {config_path} -D")
    print(f"  python {ROOT_DIR / 'swarm' / 'cli.py'} apply {config_path}")
