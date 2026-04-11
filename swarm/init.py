#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from common import ROOT_DIR


def agent_block(name: str) -> str:
    runtime_dir = Path("/tmp/nudge-swarm") / name
    return f"""## Swarm

When using the swarm workflow, read these first:
- Runtime map: `{runtime_dir / "runtime.json"}`
- Self-awareness note: `{runtime_dir / "self-awareness.txt"}`

Treat them as the source of truth for:
- tmux pane targets
- monitor sockets and live state
- babysit pid/log/spec/state files

When communicating with another tmux pane, ALWAYS use `tmux-send`.
Do NOT use raw `tmux send-keys ... Enter`.

Required form:
- `{ROOT_DIR / "tmux-send"} <target> "message"`

Reason:
- raw `tmux send-keys ... Enter` often fails to submit the Enter key
- prompts can sit unexecuted until another nudge or manual Enter

Note swarm scripts are at `{ROOT_DIR / "swarm"}`.
"""


def config_text(name: str) -> str:
    return f"""session:
  name: {name}
  window: grid

layout:
  type: grid
  rows: 1
  cols: 1

panes:
  - pane: "0.0"
    title: claude
    agent: claude
    command: "source ~/.bash_aliases && aiclaude"
    monitor: true
    babysit:
      enabled: false
      interval_secs: 600
      long_prompt_file: "prompts/worker_long.md"
      short_prompt_file: "prompts/worker_short.txt"
"""


def init(name: str, root: str | Path = ".", dry_run: bool = False) -> None:
    root_path = Path(root).resolve()
    swarm_dir = root_path / "swarm"
    prompts_dir = swarm_dir / "prompts"
    config_path = swarm_dir / f"{name}.yaml"
    agents_path = root_path / "AGENTS.md"

    files = {
        config_path: config_text(name),
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
    print(f"  python {ROOT_DIR / 'swarm' / 'cli.py'} apply {config_path} --dry-run")
    print(f"  python {ROOT_DIR / 'swarm' / 'cli.py'} apply {config_path}")
