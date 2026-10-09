#!/usr/bin/env python3
"""Agent-facing workflow guides for `aiswarm` / `aiswarm instructions`.

Flag docs stay in `aiswarm <cmd> --help`. These guides are procedures.
"""
from __future__ import annotations

GUIDES: dict[str, tuple[str, str]] = {}
# name -> (one-line summary, full body)


def _reg(name: str, summary: str, body: str) -> None:
    GUIDES[name] = (summary, body.strip() + "\n")


# Procedure guide, not the command index. Index order lives in cli._HELP_ORDER
# and bare_help(). Do not reorder this lifecycle to match -h.
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

`shell_command` may be a `provider:role` token from `swarm/models.yaml` (`codex:heavy`). The whole value must match a key. Anything else, including a full command, is launched as written. Model ids and launch flags live in that file. A config that uses no tokens does not read the table. `aiswarm init` writes `provider:role`, then `heavy`, then the bare agent name when a role is missing. A one-pane agent still uses `heavy`. `aiswarm start` prints each expansion and any unknown-token warning.

In the **nudge** implementer repo, package code is `swarm/`. The live harness is
`.aiswarm/config.yaml` (or `$AISWARM_CONFIG`).

### Common lifecycle

```bash
aiswarm init <name>          # once per project
aiswarm start                # tmux grid + monitors + comms workers
aiswarm babysit start        # optional idle prompt loops (--for 1h to auto-stop)
aiswarm tasks start          # poll backlog → free panes (--for 1h to auto-stop)
aiswarm status --brief
aiswarm swarms               # discover swarms on this machine (active/inactive)
aiswarm send 0.2 "msg"       # durable poke via log
aiswarm send any "msg"       # one eligible idle pane claims it
aiswarm send heavy "msg"     # same, only panes with category `heavy`
aiswarm send other:0.1 "msg" # cross-swarm qualified send (delivered on idle)
aiswarm send --at +2h 0.2 "msg" # deferred/scheduled send (ISO or +Nh/+Nm/+Ns)
aiswarm babysit stop
aiswarm tasks stop
aiswarm stop                 # workers + session teardown
```

### Channels (use the right one)

| Channel | Use for | Not for |
|---|---|---|
| `aiswarm send` / log | Short poke, wake, or single-consumer `any` work | Large diffs, long reports |
| Backlog task | Goal, AC, notes, follow-up tasks, final-summary, Done | Live streaming chat |
| `aiswarm capture` / `wait` | Snapshot, or block until monitor idle | Attach/stream; source of record |
| babysit | Periodic continue / clear nudges | Assigning real work units |
| tasks dispatcher | Claim To Do backlog onto free panes | Peer A→B ad-hoc handoff |

### Hard rules

- Do **not** use raw `tmux send-keys` (Enter is unreliable). Prefer `aiswarm send` or `./tmux-send`.
- Sent by mistake? `aiswarm unsend <id>` (id printed by `send`) cancels it if not yet delivered.
- Do **not** attach/stream a peer pane. Snapshot: `aiswarm capture 0.2`. Block until idle: `aiswarm wait 0.2`.
- Human presence: `aiswarm presence` (`IN` -> ask questions; `OUT` -> autonomous progress on routine authorized tasks, do not pause for trivial approvals; seek approval if material architecture/design decision requires it).
- Done = backlog Done + notes/tasks/docs + ping. TUI findings ≠ done (`/clear` wipes them; the other pane waits).
- `session_worker.py` is one worker process per swarm session: it multiplexes comms for all panes,
  optional per-pane babysit prompts, and the tasks group. C `monitor-bin` remains per pane.
  `pane_worker.py` is only a compatibility entrypoint; `babysit.py` is no longer an entrypoint.
- Session identity / runtime map path: `aiswarm this` (resolves config; points at
  `/tmp/nudge-swarm/<session>/runtime.json` written on start).
- Provider conversation IDs: `aiswarm sessions`. Claude/Grok get `--session-id` at
  launch; others are bound via the pane PID (not newest-file-in-cwd).
  `aiswarm start --resume` splices the recorded id into the config command
  (append `-r` / `--conversation`; `codex resume <id>` then the config flags)
  and drops an existing `--session-id` first. mint sees the resume flag and
  does not append a second id. No recorded id: keep the config command.
  Plain `start` still mints.

### Next guides

- `aiswarm this` — which swarm / where is runtime.json
- `aiswarm instructions tasks` — backlog dispatcher
- `aiswarm instructions presence` — human availability & autonomy guidance
- `aiswarm <command> --help` — flags and options
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
  min_chase_secs: 60    # default = poll_secs; raise to nudge less often
  max_inflight: 2       # 0 = unlimited; still one task per free pane
  clear_on_claim: true  # default: true (sends /clear before new task prompt)
  clear_every: 0        # default: 0 (send /clear every N chases; 0 = disabled)
nudge:
  tasks:
    enabled: false   # opt this pane out
  babysit:
    enabled: false   # prefer not both on same pane (fights tasks chase)
```

### CLI

```bash
aiswarm tasks start
aiswarm tasks start --for 1h   # optional; auto-stop the group after an hour
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
  `aiswarm start` alone does not start dispatching. `aiswarm tasks start --for 1h` (also `30m`,
  `90s`, or seconds) auto-stops the group; `tasks stop` or a later untimed start clears the timer.
- **Claim pool:** with `unassigned_only` (default), only unassigned tasks are claimed. If `require_label` is set (e.g. `require_label: "auto"`), only tasks with that tag/label are claimed. Assignees in
  `tasks.skip_assignees` (default `human`) are **not** claimed/reclaimed — leave for people.
  Empty `skip_assignees: []` disables that skip. Swarm owners are `aiswarm:<session>:<pane>` only;
  never use model names as assignees.
- **Stuck / Quota Tasks:** If an agent pane crashes, quotas out, or deadlocks, `tasksctl` continues
  chasing the assigned task until healthchecks exhaust. To release a stuck task back to the free pool,
  manually unassign it: `backlog task edit TASK-NN -a "" -s "To Do"`. Or park it for a human:
  `backlog task edit TASK-NN -a human`.
- **Dependency gate:** if any dependency is not Done, the task is not claimable/chaseable.
  Assignee on the dep does not matter (In Progress, human, etc.). Link work with
  `backlog task edit TASK-NN --depends-on TASK-BLOCKER`. Park for a human:
  `backlog task edit TASK-NN -a human`. Cycles / missing dep ids still block.
- **Chase:** idle + still assigned + deps Done → short re-prompt until Done/unassign. Interval
  `min_chase_secs` (default = `poll_secs`).
- Claim = In Progress + assignee `aiswarm:<session>:<pane>` before log delivery.
- Idle alone ≠ Done. Agent marks Done (or unassigns if wrong task).

### Stalled assigned panes

After `healthcheck_chases` idle chases (default 3), tasks sends one durable HEALTHCHECK nonce.
Reply from the agent with `aiswarm healthcheck pong <pane> <nonce>`; consumer delivery acks are
not liveness. No pong before `healthcheck_timeout_secs` (300 by default) respawns that pane only,
rewires its monitor, and queues a chase. `healthcheck_max_restarts` (default 1) limits this path.
It is not a continuous heartbeat and does not inspect provider error strings.
""",
)

_reg(
    "presence",
    "Human availability state, overrides, and agent autonomy guidance",
    """
## Human Presence and Agent Autonomy

`aiswarm presence` provides human presence state (IN vs OUT) so agents can calibrate their behavior:

- **When Human is IN:** Value their time. Interrogate, clarify ambiguities, ask questions, and don't make them wait.
- **When Human is OUT:** High autonomy on routine tasks. Do NOT stop or end turns asking "Does this look good?" or waiting for approvals on routine steps. Make reasonable decisions, document assumptions in backlog notes or commits, and proceed. If a material architectural decision explicitly requires human approval, document it and move to other work or idle.

### Modes and Scopes

- **Global Scope (`aiswarm presence global [in|out|auto]`):**
  - `auto`: Passive detection from `tmux list-clients` across all attached terminals (default).
  - `in`: Manually pinned global IN.
  - `out`: Manually pinned global OUT.
- **Swarm-Local Scope (`aiswarm presence local [in|out|auto|global]`):**
  - `global`: Follow global state (default).
  - `in`: Pinned local IN.
  - `out`: Pinned local OUT.
  - `auto`: Passive detection scoped strictly to clients viewing this swarm's session.

### CLI

```bash
aiswarm presence                              # Show effective, local, and global presence
aiswarm presence --json                       # Programmatic JSON inspection
aiswarm presence in                           # Pin current swarm to IN
aiswarm presence out                          # Pin current swarm to OUT
aiswarm presence local global                 # Reset current swarm to follow global
aiswarm presence global out                   # Pin global to OUT
aiswarm presence global auto                  # Reset global to passive tmux auto detection
aiswarm presence in --for 2h                  # Set override with 2-hour auto-expiry
```
""",
)


def bare_help() -> str:
    # Handwritten cheat sheet for bare `aiswarm`. Command set and order must
    # match swarm/cli.py _HELP_ORDER (`aiswarm -h`). Not generated from the parser.
    # The overview "Common lifecycle" block is a procedure, not this index.
    return """aiswarm — config-driven tmux swarm for coding agents

Same commands as `aiswarm -h`, in that order. Flags: `aiswarm <command> --help`.

Lifecycle:
  aiswarm init <name>              Create .aiswarm/config.yaml + AGENTS block
  aiswarm start                    Start session, monitors, comms workers
  aiswarm stop                     Tear down workers + tmux session
  aiswarm status --brief           Pane states
  aiswarm this                     Config + runtime.json path
  aiswarm sessions                 Provider session IDs for crash resume
  aiswarm swarms                   Active/inactive swarms on this machine
  aiswarm worker restart           Reload worker code; leave tmux panes up

Messaging:
  aiswarm send [--at TIME] <target|swarm:target> "msg"
                                   Durable log message, delivered on idle
  aiswarm unsend <id>              Cancel a queued message before delivery
  aiswarm broadcast "msg"          Immediate send to agent panes
  aiswarm clear [pane]             Send '/clear' via log (default: all agent panes)
  aiswarm log                      Inspect the comms event log
  aiswarm clear-comms              Clear the event log (destructive)
  aiswarm healthcheck pong <pane> <nonce>
                                   Reply to a dispatcher healthcheck

Pane:
  aiswarm capture <pane>           Snapshot pane text
  aiswarm wait <pane>              Block until the pane monitor is idle
  aiswarm babysit start|stop       Optional idle nudges (--for 1h)
  aiswarm tasks start|status|stop  Poll backlog; assign To Do to free panes (--for 1h)

Usage:
  aiswarm presence [local|global]  Human availability state & overrides
  aiswarm quota                    Cached provider quotas
  aiswarm quota-debug <agent>      Raw and parsed usage for one agent
  aiswarm av-usage                 Agentsview token usage
  aiswarm help                     Probed model commands for installed CLIs
  aiswarm instructions             Agent guides (overview, tasks, presence)

Config (when path omitted):
  $AISWARM_CONFIG  or  walk-up .aiswarm/config.yaml  or  explicit path / -c

Prereq: aiswarm on PATH (make install-aiswarm from the nudge repo).
"""


def index() -> str:
    lines = [
        "aiswarm instructions",
        "",
        "Start here:",
        "  aiswarm instructions overview     Required first read for swarm workflow",
        "  aiswarm this                      This swarm: config + runtime.json path",
        "  aiswarm sessions                  Provider session IDs for crash resume",
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
    if key in ("observe", "handoff"):
        return (
            "No separate guide. Snapshot: `aiswarm capture <pane>`. "
            "Block until idle: `aiswarm wait <pane>`. "
            "Done: backlog + ping (TUI findings are not done). "
            "See `aiswarm instructions overview`.\n"
        )
    if key not in GUIDES:
        known = ", ".join(GUIDES)
        raise ValueError(f"unknown guide: {guide!r} (known: {known})")
    return GUIDES[key][1]
