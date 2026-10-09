#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

try:
    from .common import load_model_aliases
except ImportError:
    from common import load_model_aliases

BLOCK_START = "<!-- AISWARM/NUDGE GUIDELINES START -->"
BLOCK_END = "<!-- AISWARM/NUDGE GUIDELINES END -->"


def agent_block_body(name: str) -> str:
    runtime_dir = Path("/tmp/nudge-swarm") / name
    return f"""## Swarm

Swarm CLI: `aiswarm` (on PATH; `make install-aiswarm` from the nudge repo).

Read workflow first:
- `aiswarm` — common commands cheat sheet
- `aiswarm instructions overview` — required agent briefing
- `aiswarm instructions tasks` — backlog dispatcher
- `aiswarm instructions presence` — human availability & autonomy guidance
- `aiswarm this` — this swarm's config + runtime.json path

After start, machine map (not git): `{runtime_dir / "runtime.json"}`

Config: `.aiswarm/config.yaml` (cwd walk-up), `$AISWARM_CONFIG`, or explicit path.
Messaging: `aiswarm send <pane> "msg"` (durable log). Do NOT raw `tmux send-keys`.
Do NOT attach/stream a peer pane. Snapshot: `aiswarm capture`. Block until idle: `aiswarm wait`.
Human presence: `aiswarm presence` (`IN` -> ask questions; `OUT` -> autonomous progress on routine authorized tasks, do not pause for trivial approvals; seek approval if material architecture/design decision requires it).
TUI findings are not done: file backlog tasks/docs, ping the requester, then idle.
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
        tail = text[end_at:].strip()
        parts = [p for p in (head, block.strip(), tail) if p]
        new = ("\n\n".join(parts) + "\n") if parts else ""
        return new, "unchanged" if new == text else "updated"

    cleaned = _strip_legacy_swarm(text) if "## Swarm" in text else text
    cleaned = cleaned.rstrip()
    new = (cleaned + "\n\n" + block.strip()) if cleaned else block.strip()
    if not new.endswith("\n"):
        new += "\n"
    if not had_content:
        return new, "created"
    return new, "unchanged" if new == text else "updated"


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

WEIGHT_PROFILES: dict[str, dict[str, int]] = {
    "heavy": {"interval_secs": 7200, "clear_every": 1},
    "medium": {"interval_secs": 3600, "clear_every": 3},
    "light": {"interval_secs": 1800, "clear_every": 6},
}


def shell_alias(agent: str, weight: str = "heavy") -> str:
    """Token written into shell_command.

    Roles are heavy, medium, and light. A missing role uses heavy, then the bare agent name.
    """
    if weight not in WEIGHT_PROFILES:
        raise ValueError(f"unknown weight {weight!r}, expected one of {tuple(WEIGHT_PROFILES.keys())}")
    aliases = load_model_aliases()
    for key in (f"{agent}:{weight}", f"{agent}:heavy"):
        if key in aliases:
            return key
    return agent


FLAVOUR_SPECS: dict[str, list[tuple[str, str]]] = {
    "1x1": [("codex", "heavy")],
    "2x2": [("codex", "heavy"), ("codex", "light"), ("claude", "heavy"), ("claude", "light")],
    "3x2": [
        ("codex", "heavy"),
        ("codex", "light"),
        ("claude", "heavy"),
        ("claude", "light"),
        ("antigravity", "light"),
        ("grok", "heavy"),
    ],
    "3x3": [
        ("codex", "heavy"),
        ("codex", "medium"),
        ("codex", "light"),
        ("claude", "heavy"),
        ("claude", "light"),
        ("grok", "heavy"),
        ("antigravity", "light"),
        ("antigravity", "light"),
        ("antigravity", "light"),
    ],
    "4x2": [
        (agent, weight)
        for agent in ("codex", "claude", "antigravity", "grok")
        for weight in ("heavy", "light")
    ],
    "babysit": [
        (agent, weight)
        for agent in ("codex", "claude")
        for weight in ("heavy", "light")
    ],
    "demo": [
        (agent, "heavy")
        for agent in ("codex", "claude", "antigravity", "grok", "vibe", "copilot")
    ],
}

FLAVOURS = tuple(FLAVOUR_SPECS.keys())


def _pane_entry(agent: str, weight: str = "heavy", *, tasks: bool = False, babysit: bool = False) -> str:
    profile = WEIGHT_PROFILES[weight]
    cmd = shell_alias(agent, weight)
    title = f"{agent} {weight}"
    lines = [
        f'      - shell_command: "{cmd}"',
        "        nudge:",
        f"          title: {title}",
        f"          agent: {agent}",
        "          monitor: true",
        f"          categories: [{weight}, {agent}]",
    ]
    if babysit:
        lines.extend([
            "          babysit:",
            "            enabled: false",
            f"            interval_secs: {profile['interval_secs']}",
            f"            clear_every: {profile['clear_every']}",
            "            long_prompt_file: prompts/worker_long.md",
            "            short_prompt_file: prompts/worker_short.txt",
        ])
    if tasks:
        lines.extend([
            "          tasks:",
            "            enabled: true",
        ])
    return "\n".join(lines) + "\n"


def _operator_pane(title: str, cmd: str) -> str:
    return f"""      - shell_command: "{cmd}"
        nudge:
          title: {title}
          monitor: false
"""


SHELL_PANE = _operator_pane("shell", "bash")
# Demo shell: no profile/rc (avoids user@host PS1) + plain prompt.
DEMO_SHELL_PANE = _operator_pane("shell", "env PS1='$ ' bash --norc --noprofile")
LOG_PANE = _operator_pane("log", "aiswarm log -w")


def config_text(name: str, agents: list[str] | None = None, flavour: str | None = None) -> str:
    if flavour == "demo":
        specs = FLAVOUR_SPECS["demo"]
        panes_block = (
            "".join(_pane_entry(a, w, tasks=True) for a, w in specs)
            + LOG_PANE
            + DEMO_SHELL_PANE
        )
        return f"""session_name: {name}
tasks:
  source: backlog
  backlog_dir: ../backlog
  ingest: [To Do]
  poll_secs: 30
  min_chase_secs: 30
  unassigned_only: true
  require_idle: true
  via_log: true
windows:
  - window_name: grid
    layout: tiled
    panes:
{panes_block}"""

    if flavour is not None:
        if flavour not in FLAVOUR_SPECS:
            raise ValueError(f"unknown flavour {flavour!r}, expected one of {FLAVOURS}")
        specs = FLAVOUR_SPECS[flavour]
        panes = [_pane_entry(a, w, babysit=(flavour == "babysit")) for a, w in specs]
        if flavour in ("2x2", "babysit"):
            panes.append(SHELL_PANE)
        panes_block = "".join(panes)
    else:
        chosen_agents = DEFAULT_AGENTS if agents is None else agents
        panes_block = "".join(_pane_entry(a, "heavy") for a in chosen_agents)

    return f"""session_name: {name}
# tasks:
#   require_label: "auto"     # Optional: only claim backlog tasks tagged with this label
windows:
  - window_name: grid
    layout: tiled
    panes:
{panes_block}"""


def init(
    name: str,
    root: str | Path = ".",
    dry_run: bool = False,
    agents: list[str] | None = None,
    flavour: str | None = None,
    force: bool = False,
) -> None:
    root_path = Path(root).resolve()
    # Consumer harness dir (not the aiswarm Python package). Default discovery: .aiswarm/config.yaml
    aiswarm_dir = root_path / ".aiswarm"
    prompts_dir = aiswarm_dir / "prompts"
    config_path = aiswarm_dir / "config.yaml"
    agents_path = root_path / "AGENTS.md"

    files = {
        config_path: config_text(name, agents, flavour=flavour),
        prompts_dir / "worker_long.md": (
            "Continue the assigned work. Read AGENTS.md; for swarm ops run "
            "`aiswarm instructions overview`. Session paths: `aiswarm this`. "
            "TUI findings are not done — file backlog/docs and ping.\n"
        ),
        prompts_dir / "worker_short.txt": "Continue. Stay in role and keep the current thread moving.\n",
    }

    for path, content in files.items():
        if path.exists() and not force:
            print(f"exists: {path}")
            continue
        if dry_run:
            action = "overwrite" if path.exists() else "create"
            print(f"would {action}: {path}")
            continue
        action = "overwritten" if path.exists() else "created"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"{action}: {path}")

    write_agents_block(agents_path, name, dry_run=dry_run)

    print()
    print("Next (config is discovered from .aiswarm/config.yaml):")
    print("  aiswarm start -D")
    print("  aiswarm start")
    print(f"  # or explicit: aiswarm start {config_path.relative_to(root_path)}")
