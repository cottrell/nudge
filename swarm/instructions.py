#!/usr/bin/env python3
"""Agent-facing workflow guides for `aiswarm` / `aiswarm instructions`.

Flag docs stay in `aiswarm <cmd> --help`. These guides are procedures.
"""
from __future__ import annotations

GUIDES: dict[str, tuple[str, str]] = {}
# name -> (one-line summary, full body)


def _reg(name: str, summary: str, body: str) -> None:
    GUIDES[name] = (summary, body.strip() + "\n")


_reg(
    "overview",
    "Required first read: when/how to use aiswarm",
    """
## aiswarm overview

aiswarm runs a config-driven tmux swarm of coding agents with activity monitors,
durable log messaging, optional babysit nudges, and optional backlog task dispatch.

### Config

Resolution order:

1. Explicit path: `aiswarm status path.yaml` or `-c path.yaml`
2. `$AISWARM_CONFIG`
3. Walk-up from cwd: `.aiswarm/config.yaml`

`aiswarm init <name>` creates `.aiswarm/config.yaml` + prompts.

In the **nudge** implementer repo, package code is `swarm/`; the live harness may
still be an explicit path such as `nudgeswarm/nudge.yaml`.

### Common lifecycle

```bash
aiswarm init <name>          # once per project
aiswarm start                # tmux grid + monitors + comms workers
aiswarm babysit start        # optional idle prompt loops
aiswarm tasks start          # poll backlog → free panes (idle if empty)
aiswarm status --brief
aiswarm send 0.2 "msg"       # durable poke via log
aiswarm babysit stop
aiswarm tasks stop
aiswarm stop                 # workers + session teardown
```

### Channels (use the right one)

| Channel | Use for | Not for |
|---|---|---|
| `aiswarm send` / log | Short poke, wake, done-ping | Large diffs, long reports |
| Backlog task | Goal, AC, notes, final-summary, Done | Live streaming chat |
| Pane attach / capture | Human debug | Agent waiting on a peer |
| babysit | Periodic continue / clear nudges | Assigning real work units |
| tasks dispatcher | Claim To Do backlog onto free panes | Peer A→B ad-hoc handoff |

### Hard rules

- Do **not** use raw `tmux send-keys` (Enter is unreliable). Prefer `aiswarm send` or `./tmux-send`.
- Do **not** attach to another agent's pane and stream it; use send + backlog + done-ping
  (`aiswarm instructions handoff`).
- Completion of assigned work is **backlog status Done**, not "pane went idle".
- Session identity / runtime map path: `aiswarm this` (resolves config; points at
  `/tmp/nudge-swarm/<session>/runtime.json` written on start).

### Next guides

- `aiswarm this` — which swarm / where is runtime.json
- `aiswarm instructions handoff` — peer agent coordination
- `aiswarm instructions tasks` — backlog dispatcher
- `aiswarm <command> --help` — flags and options
""",
)

_reg(
    "handoff",
    "Peer A→B: send poke, backlog response, done-ping (no pane streaming)",
    """
## Agent-to-agent handoff

### Problem

Agent A wants B to do work. Do **not** attach to B's pane or poll its scrollback.

### Pattern

1. **A** creates/reuses a backlog task (goal + AC + reply-to pane).
2. **A** pokes B with a short send (task id + instructions).
3. **A** continues its own work.
4. **B** works from the backlog task; appends notes; sets Done + final-summary.
5. **B** pings A: short `aiswarm send` that results live in backlog.
6. **A** reads `backlog task TASK-NN --plain`.

### Templates

Request (A → B):

```text
TASK-NN for you. Read: backlog task TASK-NN --plain
Reply: backlog notes/final-summary on TASK-NN
When done: aiswarm send <my-pane> "TASK-NN done"
```

Done (B → A):

```text
TASK-NN done. See backlog task TASK-NN (final-summary).
```

Keep sends short (SMS, not attachments). Bulk content → git + backlog.

### Anti-patterns

- Spectator attach / capture loops
- Giant send payloads
- Status only in chat (clears wipe it)
- Busy-wait polling instead of a done-ping

See also backlog doc-2 in the nudge repo for a longer worked example.
""",
)

_reg(
    "tasks",
    "Backlog → free panes dispatcher (separate from babysit)",
    """
## Tasks dispatcher

Pulls real work from backlog onto free panes. Separate from babysit continue-nudges.

### Defaults (no YAML required)

- Monitored panes: **tasks enabled** (dispatcher still off until you start it)
- Shell panes (`monitor: false`): off
- Opt out: `nudge.tasks.enabled: false`
- Top-level `tasks:` optional; defaults filled on load (ingest To Do + In Progress, poll 60s, …)
- Source (v1: backlog) is an implementation detail — discovered when dispatch runs
- Needs `backlog task list|view --json` (Backlog.md BACK-545; git/main until next release)
- Dry-run prints the full resolved form: `aiswarm tasks once -D` / `start -D`

```yaml
# optional overrides only:
tasks:
  poll_secs: 30
  min_chase_secs: 300   # throttle chase re-prompts per assignment (0 = every poll)
  max_inflight: 2       # 0 = unlimited; still one task per free pane
nudge:
  tasks:
    enabled: false   # opt this pane out
  babysit:
    enabled: false   # prefer not both on same pane (fights tasks chase)
```

### CLI

```bash
aiswarm tasks start
aiswarm tasks status
aiswarm tasks once -D      # dry-run: resolved config + planned claims
aiswarm tasks stop
```

### Behaviour

- **New work:** every pass pairs candidates with free panes, at most one task per pane.
  A free pane has no local assignment or pending comms-log event and is idle when
  `require_idle: true` (the default); monitor-unknown panes are also eligible.
- With N free panes and M candidates, the pass claims `min(N, M)` tasks, subject to the remaining
  `max_inflight` capacity. `max_inflight: 0` means unlimited overall, not multiple tasks per pane.
  Example: 3 free panes and 10 To Dos claims 3 now; the other 7 wait for a later poll and a free
  slot.
- The dispatcher never dumps the whole To Do list onto one pane or queues another task on a pane
  while it is assigned. Start it explicitly with `aiswarm tasks start` or `aiswarm tasks once`;
  `aiswarm start` alone does not start dispatching.
- **Chase:** if pane still has that assignment and is idle → short re-prompt, throttled by
  `min_chase_secs` (default 300; not every `poll_secs`), until Done / agent unassigns / gone.
  Uses `last_chased_at` (or `claimed_at`) in tasks state.
- **Babysit interaction:** do not run babysit + tasks on the same pane. Both fire when idle and
  compete for the agent. Prefer tasks alone for backlog work; babysit for pure continue-nudges.
- Claim = In Progress + assignee `aiswarm:<session>:<pane>` before log delivery.
- Idle alone ≠ Done. Agent marks Done (or unassigns if wrong task).
""",
)


def bare_help() -> str:
    return """aiswarm — config-driven tmux swarm for coding agents

Common workflow:
  aiswarm init <name>                 Create .aiswarm/config.yaml + AGENTS block
  aiswarm start                       Start session, monitors, comms workers
  aiswarm status --brief              Pane states
  aiswarm send <pane> "msg"           Durable message via log (delivered on idle)
  aiswarm babysit start|stop          Optional idle nudges (per-pane worker)
  aiswarm tasks start|status|stop     Poll backlog; assign To Do to free panes (idle if empty)
  aiswarm stop                        Tear down workers + tmux session

Config (when path omitted):
  $AISWARM_CONFIG  or  walk-up .aiswarm/config.yaml  or  explicit path / -c

Instructions (workflow for agents):
  aiswarm this                        This swarm: config + runtime.json path
  aiswarm instructions                List guides
  aiswarm instructions overview       Start here
  aiswarm instructions handoff        Peer send + backlog + done-ping
  aiswarm instructions tasks          Backlog dispatcher

Command help (flags):
  aiswarm <command> --help

Prereq: aiswarm on PATH (make install-aiswarm from the nudge repo).
"""


def index() -> str:
    lines = [
        "aiswarm instructions",
        "",
        "Start here:",
        "  aiswarm instructions overview     Required first read for swarm workflow",
        "  aiswarm this                      This swarm: config + runtime.json path",
        "  aiswarm <command> --help          Flags and options",
        "",
        "Guides:",
    ]
    for name, (summary, _) in GUIDES.items():
        lines.append(f"  {name}")
        lines.append(f"    aiswarm instructions {name}")
        lines.append(f"      -> {summary}")
    lines.append("")
    return "\n".join(lines)


def render(guide: str | None) -> str:
    if not guide:
        return index()
    key = guide.strip().lower()
    if key not in GUIDES:
        known = ", ".join(GUIDES)
        raise ValueError(f"unknown guide: {guide!r} (known: {known})")
    return GUIDES[key][1]
