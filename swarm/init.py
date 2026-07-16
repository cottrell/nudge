#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BLOCK_START = "<!-- AISWARM/NUDGE GUIDELINES START -->"
BLOCK_END = "<!-- AISWARM/NUDGE GUIDELINES END -->"


def agent_block_body(name: str) -> str:
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

Config (default discovery):
- Project harness: `.aiswarm/config.yaml` (walk-up from cwd), or `$AISWARM_CONFIG`, or explicit path.
- Prefer: `aiswarm status` / `aiswarm send 0.2 "msg"` without typing the yaml path.

Messaging (durable, preferred):
- Use the comms log: `aiswarm send <pane> "msg"` or `aiswarm send <cfg> <pane> "msg"`.
- Inspect: `aiswarm log [--pending] [--pane 0.2]`.
- Direct/manual still works: `./tmux-send <target> "message"`.

Worker loop:
- `aiswarm start` starts the base comms worker for `monitor: true` panes.
- The worker consumes the log and delivers via `tmux-send` when the pane is idle.
- Babysit: `aiswarm babysit start|stop`. Tasks: `aiswarm tasks start|stop|status|once`.

Do NOT use raw `tmux send-keys ... Enter`.
"""


def agent_block(name: str) -> str:
    body = agent_block_body(name).rstrip() + "\n"
    return f"{BLOCK_START}\n{body}{BLOCK_END}\n"


def _strip_legacy_swarm(text: str) -> str:
    """Remove a trailing un-marked ## Swarm section (pre-marker layout)."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == "## Swarm":
            return "".join(lines[:i]).rstrip() + ("\n" if lines[:i] else "")
    return text


def upsert_agents_text(text: str, block: str) -> tuple[str, str]:
    """Return (new_text, action) where action is created|updated|unchanged."""
    block = block if block.endswith("\n") else block + "\n"
    had_content = bool(text.strip())
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    if start != -1 and end != -1 and end > start:
        end_at = end + len(BLOCK_END)
        if end_at < len(text) and text[end_at] == "\n":
            end_at += 1
        head = text[:start].rstrip()
        tail = text[end_at:].lstrip("\n")
        parts = [p for p in (head, block.rstrip("\n"), tail) if p]
        new = "\n\n".join(parts) + "\n"
        return new, "unchanged" if new == text else "updated"

    cleaned = _strip_legacy_swarm(text) if "## Swarm" in text else text
    cleaned = cleaned.rstrip()
    new = (cleaned + "\n\n" + block) if cleaned else block
    if not new.endswith("\n"):
        new += "\n"
    if not had_content:
        return new, "created"
    return new, "updated"


def remove_agents_text(text: str) -> tuple[str, bool]:
    """Remove marked AISWARM block. Returns (new_text, removed)."""
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    if start == -1 or end == -1 or end < start:
        return text, False
    end_at = end + len(BLOCK_END)
    if end_at < len(text) and text[end_at] == "\n":
        end_at += 1
    head = text[:start].rstrip()
    tail = text[end_at:].lstrip("\n")
    if head and tail:
        new = head + "\n\n" + tail
    else:
        new = head + ("\n" if head else "") + tail
    if new and not new.endswith("\n"):
        new += "\n"
    return new, True


def resolve_agents_md(start: Path) -> Path | None:
    """Walk up from start (file or dir) looking for AGENTS.md."""
    base = start if start.is_dir() else start.parent
    for d in [base, *base.parents]:
        candidate = d / "AGENTS.md"
        if candidate.is_file():
            return candidate
    return None


def write_agents_block(agents_path: Path, name: str, dry_run: bool = False) -> str:
    """Upsert managed block into AGENTS.md. Returns action string."""
    block = agent_block(name)
    if agents_path.exists():
        old = agents_path.read_text()
        new, action = upsert_agents_text(old, block)
    else:
        new, action = block, "created"
    if dry_run:
        print(f"would {action}: {agents_path}")
        if action != "unchanged":
            print()
            print(block.rstrip())
        return action
    if action == "unchanged":
        print(f"AGENTS.md unchanged: {agents_path}")
        return action
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    agents_path.write_text(new)
    print(f"{action}: {agents_path}")
    return action


def remove_agents_block(agents_path: Path, dry_run: bool = False) -> bool:
    """Remove managed block from AGENTS.md if present. Returns whether removed."""
    if not agents_path.is_file():
        return False
    old = agents_path.read_text()
    new, removed = remove_agents_text(old)
    if not removed:
        return False
    if dry_run:
        print(f"would remove AISWARM block: {agents_path}")
        return True
    agents_path.write_text(new)
    print(f"removed AISWARM block: {agents_path}")
    return True


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
    # Consumer harness dir (not the aiswarm Python package). Default discovery: .aiswarm/config.yaml
    aiswarm_dir = root_path / ".aiswarm"
    prompts_dir = aiswarm_dir / "prompts"
    config_path = aiswarm_dir / "config.yaml"
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

    write_agents_block(agents_path, name, dry_run=dry_run)

    print()
    print("Next (config is discovered from .aiswarm/config.yaml):")
    print("  aiswarm start -D")
    print("  aiswarm start")
    print(f"  # or explicit: aiswarm start {config_path.relative_to(root_path)}")
