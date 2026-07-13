#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


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

Swarm CLI: `aiswarm`
Prereq: `aiswarm` must be on `PATH`; install it with `make install-aiswarm`.

Messaging (durable, preferred):
- Use the comms log for reliability between agents: `aiswarm send <cfg> <pane> "msg"` or `log_broadcast`.
- Inspect: `aiswarm log <cfg> [--pending] [--pane 0.2]`, `aiswarm cursors <cfg>`.
- Direct/manual still works: `./tmux-send <target> "message"`.

Worker loop:
- `aiswarm start <cfg>` starts the base comms worker for `monitor: true` panes.
- The worker consumes the log and delivers via `tmux-send` when the pane is idle.
- Babysit prompt nudges are independent; use `aiswarm babysit start|stop <cfg>`.

Do NOT use raw `tmux send-keys ... Enter`.

Swarm scripts: `swarm/`.
"""


DEFAULT_AGENTS = ["codex", "claude", "antigravity", "grok"]

AGENT_COMMANDS: dict[str, str] = {
    "claude": "claude --dangerously-skip-permissions",
    "codex": "codex --dangerously-bypass-approvals-and-sandbox",
    "gemini": "gemini -y",
    "grok": "grok --always-approve -m grok-build",
    "antigravity": "agy --dangerously-skip-permissions",
    "copilot": "copilot --allow-all-tools",
    "vibe": "vibe --agent auto-approve",
}

AGENT_LIGHT_COMMANDS: dict[str, str] = {
    "claude": "claude --dangerously-skip-permissions --model haiku",
    "codex": "codex --dangerously-bypass-approvals-and-sandbox -m gpt-5.4-mini",
    "gemini": "gemini -y -m gemini-2.5-flash",
    "grok": "grok --always-approve",
    "antigravity": "agy --dangerously-skip-permissions --model mini",
}

FLAVOUR_AGENTS: dict[str, list[str]] = {
    "3x2": ["codex", "claude", "antigravity", "grok"],
    "2x2": ["codex", "claude"],
}


def _pane_entry(agent: str, weight: str = "heavy") -> str:
    if weight == "light":
        cmd = AGENT_LIGHT_COMMANDS.get(agent, AGENT_COMMANDS.get(agent, agent))
        title = f"{agent} light"
        interval = 1800
        clear_every = "\n            clear_every: 6"
    else:
        cmd = AGENT_COMMANDS.get(agent, agent)
        title = f"{agent} heavy" if weight == "heavy" else agent
        interval = 7200
        clear_every = "\n            clear_every: 1"
    return f"""      - shell_command: "{cmd}"
        nudge:
          title: {title}
          agent: {agent}
          monitor: true
          babysit:
            enabled: false
            interval_secs: {interval}{clear_every}
            long_prompt_file: prompts/worker_long.md
            short_prompt_file: prompts/worker_short.txt
"""


SHELL_PANE = """      - shell_command: "bash"
        nudge:
          title: shell
          monitor: false
"""


def config_text(name: str, agents: list[str] | None = None, flavour: str | None = None) -> str:
    if flavour == "3x2":
        flavour_agents = FLAVOUR_AGENTS["3x2"]
        # codex+claude: heavy+light; antigravity+grok: solo
        panes_block = (
            "".join(_pane_entry(a, w) for a in ["codex", "claude"] for w in ("heavy", "light"))
            + _pane_entry("antigravity", "solo")
            + _pane_entry("grok", "solo")
        )
    elif flavour == "2x2":
        flavour_agents = FLAVOUR_AGENTS["2x2"]
        panes_block = (
            "".join(_pane_entry(a, w) for a in flavour_agents for w in ("heavy", "light"))
            + SHELL_PANE
        )
    else:
        if agents is None:
            agents = DEFAULT_AGENTS
        panes_block = "".join(_pane_entry(a, "solo") for a in agents)
    return f"""session_name: {name}
windows:
  - window_name: grid
    layout: tiled
    panes:
{panes_block}"""


def init(name: str, root: str | Path = ".", dry_run: bool = False, agents: list[str] | None = None, flavour: str | None = None) -> None:
    root_path = Path(root).resolve()
    swarm_dir = root_path / "swarm"
    prompts_dir = swarm_dir / "prompts"
    config_path = swarm_dir / f"{name}.yaml"
    agents_path = root_path / "AGENTS.md"

    files = {
        config_path: config_text(name, agents, flavour=flavour),
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
    print(f"  aiswarm start swarm/{name}.yaml -D")
    print(f"  aiswarm start swarm/{name}.yaml")
