# nudge

<p align="center">
  <img src="assets/favicon-mural-droid.jpg" alt="Kratos and Bia force an idle agent-droid back to work" width="220" />
</p>

Yet another multi-agent-in-tmux setup — kept small on purpose: **comms**
(tmux-send + durable log, deliver on idle), **loops** (babysit nudges + backlog
→ free panes), and **best-effort quota** pacing. Config-driven YAML/tmuxp grids
and a tiny activity monitor (`working` / `idle`). Not a full control plane.

<p align="center">
  <img src="assets/demo.gif" alt="aiswarm demo: init, start, shell-pane sends and backlog task dispatch" width="720" />
  <br />
  <sub>Demo (3× speed): <code>aiswarm init --flavour demo</code> → start → shell-pane ops / backlog tasks · <a href="assets/demo.mp4">mp4</a></sub>
</p>

Daily driver **and** loop harness: the same panes are where you sit and work
with agents by hand (Claude, Codex, Grok, …), and where idle-gated comms /
babysit / tasks keep things moving when you step back. Personal multi-agent
workflows; works standalone.

Primary workflow is the installed `aiswarm` command. From a repo checkout,
`python -m swarm.cli` or `python swarm/cli.py` also works.

`aiswarm` must be on `PATH`; from this repo, run `make install-aiswarm`.

```bash
aiswarm                      # workflow cheat sheet
aiswarm instructions         # agent guides index
aiswarm instructions overview
aiswarm this                 # this swarm: config + runtime.json path
aiswarm <command> --help     # flags
```

Install `aiswarm` into your `uv` tool environment:

```bash
make install-aiswarm
```

### Default config (`.aiswarm/config.yaml`)

Consumer projects: harness lives under **`.aiswarm/`** (not the Python package).

Resolution order for commands that need a config:

1. Explicit path (`aiswarm status path/to.yaml` or `-c path/to.yaml`)
2. `$AISWARM_CONFIG`
3. Walk up from cwd for **`.aiswarm/config.yaml`**

```bash
aiswarm init myproject          # writes .aiswarm/config.yaml + prompts (commit if team-shared)
aiswarm start                   # no path needed inside the project
aiswarm send 0.0 "hello"        # same
aiswarm status nudgeswarm/nudge.yaml   # explicit still works (e.g. this implementer repo)
```

Note: in **this** repo, `./swarm/` is package **code**. Live harness is still
`nudgeswarm/` until you migrate; use an explicit path or `$AISWARM_CONFIG` here.

States: `unknown` `working` `idle`

## Workflow

```bash
# 1. Create a starter config and AGENTS note (once per project)
aiswarm init <project>
```

```bash
# 2. Turn on the swarm (tmux session + panes + per-pane monitors + worker loops)
#    This is a "create" for the tmux grid, not a declarative update: if you change
#    pane/window counts in the YAML after the swarm is running, `start` will refuse
#    and tell you to recreate the session. Worker/monitor config is more forgiving
#    on re-start.
aiswarm start                   # uses .aiswarm/config.yaml when present
# aiswarm start ./path/to.yaml  # explicit override
```

Architecture notes: one tmux *session* per YAML file (`session_name`); one *monitor*
(activity detector via monitor-bin) per `monitor: true` pane, each with its own Unix
socket `/tmp/<session>_<W.N>.sock`; comms workers (log consumers that deliver on idle)
start for monitored panes. Babysit is **not** turned on by `start`.

```bash
# 3. Turn on babysit for panes that have `babysit.enabled: true` in the YAML
aiswarm babysit start
# aiswarm babysit stop    turns babysit back off; swarm/monitors/comms stay up
```

```bash
# 3b. Optional: pull real work from backlog into free panes (separate from babysit)
#     Monitored panes: tasks enabled by default (opt out: nudge.tasks.enabled: false)
#     Dispatcher is off until you start it; -D prints fully resolved defaults
aiswarm tasks start
aiswarm tasks status
aiswarm tasks once -D   # dry-run: resolved config + planned claims
aiswarm tasks stop
```

```bash
# 4. Full teardown: stops tasks dispatcher + workers, kills monitors, tears down tmux
aiswarm stop
```

Other useful commands:

```bash
aiswarm start --skip-grid
aiswarm status --brief -w
aiswarm broadcast "AGENTS.md updated; please re-read it."
aiswarm broadcast --via-log "use durable log"    # write to event log instead of direct send
aiswarm send 0.0 "hello via log"                 # durable, delivered on idle
aiswarm log --pending
aiswarm cursors
aiswarm clear-comms -y
aiswarm quota
aiswarm av-usage
# explicit path still ok: aiswarm status ./nudgeswarm/nudge.yaml
```

Note: broadcast and log-delivered messages are sent literally. Do not add synthetic sender prefixes, and keep slash commands like `/clear` unchanged. Direct/manual sends still work with `tmux-send`; prefer it (or the log commands) over raw `tmux send-keys`.

### Agent-to-agent handoff (do not stream peer panes)

Prefer short `aiswarm send` pokes + durable results in backlog + a short done-ping, instead of attaching to another agent's tmux pane and waiting on its stream.

See `backlog/docs/doc-2 - Agent-to-agent-handoff-via-send-backlog-and-ping.md` for the full example workflow and message templates.

Status/usage reliability note:

- monitor state is activity-based: any pane output means `working`; 10 seconds without output means `idle`
- output content is not classified, so agent UI text changes do not affect state detection
- quiet long-running commands can appear idle, while continuous idle-screen redraws can appear working
- `usage` is handled separately and remains best-effort; treat it as an operator hint

Attach after start if needed:

```bash
aiswarm start --attach
```

tmuxp-first flow:

```bash
tmuxp load .aiswarm/config.yaml
aiswarm start --skip-grid
```

Built-in examples:

- `examples/swarm-single.yaml`
- `examples/swarm-grid.yaml`

## Config model

- one tmux session
- one or more tmux windows
- each window has `window_name`, `layout`, and `panes`
- pane command is `shell_command`
- nudge metadata is under `nudge.*` (`title`, `agent`, `monitor`, `babysit`, `comms`, `tasks`)
- `comms.enabled` (defaults to `monitor`) starts a per-pane worker that consumes the durable log and delivers on idle
- optional top-level `tasks:` configures the session task dispatcher (v1 source: backlog)

Notes:

- pane IDs are derived as `W.N` (window index, pane index)
- `start` creates the tmux grid (session/windows/panes) according to the YAML.
  It is **not** safe to re-run after changing pane counts or layout on a live session
  (you'll be told to recreate the session).
- One monitor per `monitor: true` pane (started by `start`)
- `start` ensures the base worker loop (comms/message delivery) for monitored panes.
- `babysit start` enables the babysit prompt group (nudges etc.) for panes with `babysit.enabled: true`.
  It does not affect the base comms worker loop.
- `tasks start` runs a **session-level** dispatcher (not folded into babysit) that lists backlog
  tasks matching `tasks.ingest` (default: `To Do` + `In Progress`), claims them, and delivers a prompt via
  the durable log to free monitored panes (tasks enabled by default; opt out with
  `nudge.tasks.enabled: false`).
- `start`, `babysit start`, and `tasks start` write runtime files under `/tmp/nudge-swarm/<session>/`
- runtime map: `/tmp/nudge-swarm/<session>/runtime.json` (path via `aiswarm this`)
- tasks dispatcher state: `/tmp/nudge-swarm/<session>/tasks/`

## Tasks dispatcher (backlog → free panes)

Why: fixed babysit “please continue” prompts waste tokens when real work already lives in backlog.
The orchestrator must touch backlog itself (list + claim) so agents only receive a concrete task
when free. Delivery uses the durable log so the existing idle consumer still gates tmux-send.
Uses `backlog task list|view --json` only (Backlog.md BACK-545; git/main until the next release after 1.48.0 — do not scrape `--plain`).

```yaml
# top-level (session)
tasks:
  source: backlog                 # v1 only; name stays generic for future sources
  backlog_dir: ../backlog         # optional; walks up for backlog/config.yml if omitted
  ingest: [To Do, In Progress]    # default; In Progress lets a restarted dispatcher recover claims
  poll_secs: 60
  min_chase_secs: 60              # min between chase re-prompts; default = poll_secs
  unassigned_only: true
  require_label: null             # e.g. auto — only tasks with this label
  claim_assignee_prefix: aiswarm  # assignee becomes aiswarm:<session>:<pane>
  require_idle: true
  via_log: true
  max_inflight: 0                 # 0 = unlimited; still one task per free pane

windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: false        # prefer not both on same pane (fights tasks chase)
          tasks:
            enabled: true
```

```bash
aiswarm tasks start
aiswarm tasks status
aiswarm tasks once
aiswarm tasks stop
```

Claim happens **before** log delivery (`In Progress` + assignee). Completion is **not** inferred
from pane idle — the agent (or human) marks the task Done via the backlog CLI. Local assignment
state is cleared on the next poll when status is Done.

- **Dependency gate:** a task is runnable only when its backlog dependencies are complete
  (default: `Done`). If a task is waiting on a blocker or review, add that task as a dependency
  with `backlog task edit TASK-NN --depends-on TASK-BLOCKER`; the dispatcher pauses claim/chase on
  the parent until the dependency clears. Cycles and missing dependency ids are treated as blocked
  errors.
- **Chase:** idle + still assigned + deps clear → short re-prompt until Done/unassign. Interval is
  `min_chase_secs` (default same as `poll_secs`). Raise it only if you need fewer nudges.

Each `tasks once` pass (and each poll from `tasks start`) assigns **at most one task to each free
pane**. A pane is free when it has no local assignment or pending comms-log event and, by default,
is idle (`require_idle: true`; monitor-unknown panes are also eligible). With N free panes and M
candidate tasks, the pass claims `min(N, M)` tasks, further limited by `max_inflight` when it is
greater than zero. For example, 3 free panes and 10 To Dos claims 3 tasks this pass; the other 7
wait until a later poll finds a newly free slot.

The dispatcher does not dump the whole To Do list onto one pane and does not queue multiple tasks
on a pane while it has an assignment. `aiswarm start` does not start this dispatcher; run
`aiswarm tasks start` (or a single `aiswarm tasks once`) explicitly.

### Stalled assigned panes

After `healthcheck_chases` idle chases (default 3), the dispatcher sends one durable `HEALTHCHECK`
with a nonce. The agent replies with `aiswarm healthcheck pong <pane> <nonce>`; consumer delivery
acks do not count. No pong before `healthcheck_timeout_secs` (default 300) restarts only that pane,
re-attaches its monitor, and queues a chase. `healthcheck_max_restarts` (default 1) caps retries;
then the dispatcher leaves the assignment for an operator or later peer-checkup path. This is not a
continuous heartbeat and never scrapes provider-specific error text.

## Babysit quota pacing

When `babysit.enabled: true` and `agent` is one of `claude`, `codex`, or `agy`, the
babysitter samples remaining quota every `quota_probe_secs` seconds (default 300) and
uses an exponential moving average (EMA) to pace nudge intervals so quota is spread
evenly until the provider reset.

How it works:
- After each nudge the babysitter measures how much quota was consumed (`C = pct_before - pct_after`)
- EMA tracks the mean (`μ`) and variance (`σ`) of consumption per nudge
- Nudge interval: `τ = (time_to_reset × (μ + k_var × σ)) / (quota_remaining × safety)`
- For the first `ema_warmup` nudges the fixed `interval_secs` is used while the EMA warms up
- The quota cache is pre-warmed in a background thread so probes never block the main loop

YAML knobs (all optional, defaults shown):

```yaml
babysit:
  quota_probe_secs: 300   # how often to sample quota
  ema_alpha: 0.30         # smoothing factor (higher = reacts faster)
  ema_safety: 0.92        # target fraction of quota (leaves ~8% buffer)
  ema_k_var: 0.0          # variance weight; raise to 0.5–1.0 for conservative pacing
  ema_warmup: 3           # nudges before EMA replaces fixed interval
  ema_min_wait: 30        # hard floor (seconds)
  ema_max_wait: 1200      # hard ceiling (seconds)
```

The EMA is noisy when multiple swarms share the same provider quota — each instance
independently estimates its own consumption rate. This is intentional: overestimation
biases toward slower nudging, which is the right direction when quota is shared.

## Build and test

```bash
make build
make test
make test-c
make test-swarm
```

Python helpers live in `pyproject.toml`:

```bash
uv sync
```

## Capture fixtures

Fixture replay tests depend on real captured agent output in `fixtures/*_capture.txt`.

Fixtures now exercise real terminal byte streams rather than expected UI patterns.
Re-capture when replay tests expose an input-handling issue or fixtures become stale.

Commands:

```bash
make capture AGENT=claude DUR=60
make capture_codex DUR=60
make capture_copilot DUR=60
make capture_gemini DUR=60
make capture_vibe DUR=60
make capture_qwen DUR=60
make capture_grok DUR=60
make capture_all DUR=60
```

Practical cadence: re-capture on breakage or visible upstream CLI changes, not on a fixed schedule.

## Backend

`monitor-bin` is the only monitor implementation. Low-level helpers used by the
swarm tooling directly (rarely needed by hand): `attach.sh` (monitor attach to
pane), `tmux-send` (safe text+Enter send).

Debug helpers:

```bash
MONITOR_DEBUG=1 ./attach.sh mysession claude
MONITOR_STATE_LOG=1 ./attach.sh mysession claude
MONITOR_IDLE_SECS=20 ./attach.sh mysession claude
```

Defaults:

- `MONITOR_DEBUG=1` writes raw lines to `/tmp/<session>_<window-pane>.raw`
- `MONITOR_STATE_LOG=1` writes transitions to `/tmp/<session>_<window-pane>.state.log`
- `MONITOR_IDLE_SECS` controls the quiet period before `idle` (default: 10)

The monitor deliberately reports activity, not semantic agent status: for all
agents except `grok`, any pane output means `working` until the quiet timeout,
while `grok` still relies on parsing OSC terminal-title updates where title
`grok` means `idle` and any other title means `working`.

## Rough edges / limitations

Most of these are intentional trade-offs or already documented inline above:

- Changing pane counts / layout after `start` requires a full session recreate
  (`start` is create-oriented, not a declarative grid update)
- Monitor is activity-based only (not semantic agent status); quiet long jobs can
  look idle, busy idle-screen redraws can look working
- Quota EMA pacing is noisy when multiple swarms share one provider quota
  (overestimates → slower nudges; usually the safe direction)
- `usage` / quota reporting is best-effort operator hint, not a hard scheduler

See `backlog/tasks/` for planned work. Contributions welcome via issues or PRs
(see `AGENTS.md`).

## Similar projects

The space of “run many coding agents in parallel” is large and growing (see
[awesome-agent-orchestrators](https://github.com/andyrewlee/awesome-agent-orchestrators)).
nudge sits in a narrower slice: **config-driven tmux swarm lifecycle**, a small
**activity monitor** (`working` / `idle`), **durable log messaging delivered only
when idle**, optional **idle babysit**, and optional **backlog → free-pane** task
dispatch.

What is usually *not* the product center here (and may be elsewhere): big TUI
control planes, **one worktree per agent as the swarm model**, desktop/Electron
fleet UIs, or vendor-native agent teams.

Git worktrees are fine when an agent (or human) chooses them for a task; nudge
does not invent or require them. The default swarm is a **shared project cwd** —
coordinate via idle-gated messaging and backlog, not by forking the checkout per
pane. Peers that *do* center worktree isolation (dmux, Claude Squad, thurbox, …)
are solving a related but different problem.

### At a glance

| Project | Substrate | Summary | vs nudge |
| --- | --- | --- | --- |
| **[NTM](https://github.com/Dicklesworthstone/ntm)** | real tmux · Go | Full local control plane: spawn, dashboard, mail, safety, work graph, robot/API | Closest full-stack peer; broader operator surface |
| **[thurbox](https://github.com/Thurbeen/thurbox)** | real tmux · Rust TUI | Multi-CLI sessions, worktrees, automations, tasks, inter-session mailbox, review | Closest “productized TUI”; heavier than YAML grid + workers |
| **[dmux](https://github.com/standardagents/dmux)** | real tmux · Node | Parallel agents, **one worktree/branch per pane**, merge/PR flow | Isolation + git workflow first; not idle log gate |
| **[Claude Squad](https://github.com/smtg-ai/claude-squad)** (`cs`) | real tmux · Go TUI | Background multi-agent sessions, worktrees, diff review before apply | Session/worktree manager; not swarm log + babysit |
| **[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)** | real tmux | Hierarchy (shogun → karo → ashigaru) across many CLIs | Role tree orchestration vs declarative pane grid |
| **[Corral](https://github.com/cdknorow/corral)** | tmux + FastAPI | Self-hosted control plane for local coding agents | Server/API flavor; different packaging |
| **[herdr](https://github.com/ogulcancelik/herdr)** | own mux (Rust) | Agent-aware multiplexer, status detection, persistent workspaces | Smart terminal, not tmux YAML + log workers |
| **[tmux-ide](https://github.com/wavyrai/tmux-ide)** | real tmux | `ide.yml` layouts, agent-team templates | Layout/IDE templates; lighter orchestration loop |
| **[cmux](https://github.com/manaflow-ai/cmux)** | macOS terminal | Agent-native terminal (panes/splits), not a thin tmux wrapper | Different substrate; often compared in the same “fleet” conversation |
| **Claude Code Agent Teams** | native / tmux panes | Vendor multi-agent teams (`teammateMode`) | Claude-only product feature, not multi-provider harness |

### Closest peers (detail)

#### [NTM](https://github.com/Dicklesworthstone/ntm)

[NTM (Named Tmux Manager)](https://github.com/Dicklesworthstone/ntm) is the
closest **full-stack** cousin: local-first, tmux-centric multi-agent
orchestration for Claude / Codex / AGY / Grok. Both spawn labeled agent panes,
send work across them, and aim to make parallel coding agents manageable.

They diverge on scope and center of gravity:

| | **nudge (`aiswarm`)** | **NTM** |
| --- | --- | --- |
| **Shape** | Small Python package + C `monitor-bin`; YAML/tmuxp grids | Large Go binary; TUI dashboard/palette, REST/SSE/WS, robot CLI |
| **Core job** | Keep panes productive: activity gate → durable log delivery → optional babysit / task claim | Full local control plane: spawn, triage, mail, safety, checkpoints, pipelines |
| **Work queue** | [Backlog.md](https://github.com/Dan-Maor/backlog.md) via `aiswarm tasks` | Beads / `br` / `bv` graph triage, assign, queue-dry ideation |
| **Comms** | Per-session durable log; deliver only when pane is idle | Agent Mail + locks/reservations; human overseer mail surfaces |
| **Idle / activity** | Explicit per-pane C monitor; idle gates send | Activity/health/watch; less central to the product story |
| **Babysit** | Optional idle re-prompt loop (separate from `start` / tasks) | Not a first-class idle babysit loop |
| **Safety** | Thin (safe `tmux-send`; no policy engine) | Policy, guards, approvals |
| **Durability** | Runtime under `/tmp/nudge-swarm/…`; log cursors; backlog claims | Checkpoints, timelines, audit, pipeline resume under `.ntm/` |
| **Config** | Project `.aiswarm/config.yaml` (tmuxp-compatible + `nudge.*`) | `~/.config/ntm/` + project `.ntm/` |
| **Deps** | `tmux`, agent CLIs; optional backlog | Intentionally integration-heavy (`br`, `bv`, Agent Mail, …) |
| **When to prefer** | Lean swarm harness, idle-gated messaging, backlog dispatch | Operator dashboard, work-graph intelligence, safety/audit, APIs |

Overlap: both treat tmux as the runtime for multi-agent coding.
nudge optimizes for a small, config-driven “keep the swarm moving” loop;
NTM optimizes for a broad operator control plane around that same idea.

#### [thurbox](https://github.com/Thurbeen/thurbox)

[thurbox](https://github.com/Thurbeen/thurbox) is the closest **productized TUI**
peer: multi-CLI agents in **real tmux** (or psmux on Windows), git worktrees,
automations, built-in tasks, inter-session mailbox + wake nudges, native code
review, headless `thurbox-cli`, optional SSH hosts. Agent definitions are data
(`agents.toml`).

| | **nudge** | **thurbox** |
| --- | --- | --- |
| **Shape** | CLI + YAML; small Python + C monitor | Rust TUI + CLI; SQLite-backed session state |
| **Core job** | Declarative swarm grid + idle-gated workers | Operator TUI for many persistent agent sessions |
| **Isolation** | Shared cwd unless you arrange worktrees yourself | First-class worktrees, multi-repo sessions |
| **Comms** | Durable log, deliver on idle | Inter-session mailbox with claim/drain + wake |
| **Work** | Optional backlog claim → free pane | Built-in tasks + automations (cron/send/spawn) |
| **Activity gate** | Central (`monitor-bin` → idle delivery) | Metrics/info panel; not the same “only send when quiet” model |
| **When to prefer** | Scriptable YAML harness, idle-gated sends, backlog integration | Rich session UX, review, multi-repo, automations, Windows/SSH |

Overlap: real tmux, any coding CLI, messaging, keep many agents alive.
nudge stays smaller and more “workers around a YAML grid”; thurbox is a full
session product with review and automation surfaces.

#### [dmux](https://github.com/standardagents/dmux)

[dmux](https://github.com/standardagents/dmux) is a strong **worktree-isolation**
peer: each pane gets its own git worktree and branch; multi-agent launch, merge
and PR helpers, file browser, multi-project panes. Wide agent CLI support.

| | **nudge** | **dmux** |
| --- | --- | --- |
| **Shape** | Config-first (`aiswarm` + YAML) | Interactive TUI (`dmux`, `n` new pane) |
| **Core job** | Swarm lifecycle + idle messaging + task claim | Parallel tasks without git collisions |
| **Isolation** | Optional / external | Default (worktree + branch per pane) |
| **Comms / babysit** | Durable log + optional idle babysit | Pane management; not the same durable idle queue |
| **When to prefer** | Coordinated swarm on a shared tree + backlog | Many independent tasks, merge/PR as the endgame |

Overlap: tmux + multi-CLI parallel coding.
dmux optimizes for **branch isolation and merge UX**; nudge optimizes for
**shared-grid coordination and idle-gated delivery**.

#### [Claude Squad](https://github.com/smtg-ai/claude-squad) (`cs`)

[Claude Squad](https://github.com/smtg-ai/claude-squad) is a mature **session
manager** TUI: tmux sessions + git worktrees, background agents (Claude, Codex,
Gemini, Aider, …), attach/diff/checkout/resume, optional auto-yes.

| | **nudge** | **Claude Squad** |
| --- | --- | --- |
| **Shape** | YAML grid + CLI workers | Single TUI (`cs`) over many sessions |
| **Core job** | Keep a fixed swarm productive | Spin up/manage many background tasks |
| **Isolation** | Not the product center | Worktree per instance by default |
| **Messaging / tasks** | Durable log, babysit, backlog dispatch | Session list + diff review; less swarm mailbox |
| **When to prefer** | Long-lived multi-pane swarm with log routing | Many one-off tasks in isolated workspaces |

Overlap: tmux-backed multi-agent coding with a human overview.
Claude Squad is **instance lifecycle + worktrees**; nudge is **grid + idle
workers + optional task feed**.

#### [multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)

[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun) runs a
**hierarchy** of coding CLIs in tmux (shogun → karo → ashigaru), multi-provider
(Claude, Codex, Copilot, Kimi, …), with coordination meant to stay cheap
(local, not an extra LLM control plane).

| | **nudge** | **shogun** |
| --- | --- | --- |
| **Shape** | Flat YAML panes + roles via prompts/config | Explicit feudal role tree |
| **Core job** | Idle-gated swarm + backlog claim | Hierarchical parallel army |
| **When to prefer** | Declarative grid you start/stop as a unit | Role-based multi-agent theater in tmux |

### Other related tools

Status / indicators / light managers:

- [ccmanager](https://github.com/kbwo/ccmanager)
- [tallr](https://github.com/kaihochak/tallr)
- [agent-tmux-monitor](https://github.com/damelLP/agent-tmux-monitor)
- [tmuxcc](https://github.com/nyanko3141592/tmuxcc)
- [agent-deck](https://github.com/asheshgoplani/agent-deck)
- [agent-of-empires](https://github.com/njbrake/agent-of-empires)
- [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator)
- [tcmux](https://github.com/k1LoW/tcmux)

General session layout (not agent-specific):

- [tmuxp](https://tmuxp.git-pull.com/)
- [tmuxinator](https://github.com/tmuxinator/tmuxinator)
- [teamocil](https://github.com/remiprev/teamocil)
- [Zellij](https://zellij.dev/)
