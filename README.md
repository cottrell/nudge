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

## Design philosophy

- Shared checkout is the default. A branch or worktree is a choice, not the swarm model.
- Exit stays cheap. Git, Backlog, tmux, and provider sessions stay useful without nudge.
- Layers are optional: tmux, monitor, durable log, babysit, tasks, quota hints.
- Mechanisms stay ordinary: processes, files, SQLite, YAML, tmux, provider CLIs.
- Subscription access is the official CLI only. No OAuth, token reuse, or third-party bridges as architecture.
- Backlog and git hold the work. Nudge wakes and routes.

Primary workflow is the installed `aiswarm` command. From a repo checkout,
`python -m swarm.cli` or `python swarm/cli.py` also works.

`aiswarm` must be on `PATH`; from this repo, run `make install-aiswarm`.

```bash
aiswarm                      # workflow cheat sheet
aiswarm instructions         # agent guides index
aiswarm instructions overview
aiswarm this                 # this swarm: config + runtime.json path
aiswarm sessions             # provider session IDs (resume after a crash)
aiswarm start --resume       # relaunch panes from those IDs
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
aiswarm send any "check tests"  # one eligible idle pane receives it
aiswarm send heavy "refactor"   # one idle pane in category `heavy`
aiswarm send --at +2h 0.2 "check progress"  # deferred delivery (ISO timestamp or +Nh/+Nm/+Ns)
aiswarm status .aiswarm/config.yaml   # explicit path still works
```

Note: in **this** repo, `./swarm/` is the Python package. The live harness is
`.aiswarm/config.yaml`.

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
aiswarm babysit start --for 1h   # auto-stop the prompt group after an hour
# aiswarm babysit stop    turns babysit back off; swarm/monitors/comms stay up
```

```bash
# 3b. Optional: pull real work from backlog into free panes (separate from babysit)
#     Monitored panes: tasks enabled by default (opt out: nudge.tasks.enabled: false)
#     Dispatcher is off until you start it; -D prints fully resolved defaults
aiswarm tasks start
aiswarm tasks start --for 30m   # auto-stop the tasks group after 30 minutes
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
aiswarm send any "investigate the failure"       # durable, exactly one idle pane
aiswarm send --at +30m 0.0 "poke in 30m"         # scheduled delivery (+2h, +30m, ISO timestamp)
aiswarm send -s otherswarm 0.1 "hi from nudge"   # cross-swarm, via its runtime.json
aiswarm log --pending
aiswarm cursors
aiswarm clear-comms -y
aiswarm quota
aiswarm av-usage
# explicit path still ok: aiswarm status .aiswarm/config.yaml
```

Note: broadcast and log-delivered messages are sent literally. Do not add synthetic sender prefixes, and keep slash commands like `/clear` unchanged. Direct/manual sends still work with `tmux-send`; prefer it (or the log commands) over raw `tmux send-keys`.

`send any` is the single-consumer counterpart to broadcast. It queues immediately,
even when all panes are busy; the always-running comms worker atomically routes it
to exactly one idle monitored pane. Panes holding local Backlog task assignments
are skipped. This does not require `aiswarm tasks start`, and it does not add task
completion or chase semantics.

Scheduled messages (`send --at`): Defer message delivery with `--at <ISO timestamp|+Nh|+Nm|+Ns>` (e.g. `+2h`, `+30m`, `+45s`, `2026-10-02T12:00:00`). The message is stored in the durable event log with a not-before timestamp and delivered only after that time has passed and normal idle conditions hold. Does not cause head-of-line blocking for subsequent immediate messages. Scheduled messages appear in `aiswarm log --pending` and `aiswarm status` with their due times.

Pane categories: list labels per pane (`nudge.categories: [heavy, claude]`, several
allowed). `aiswarm send heavy "msg"` is `send any` restricted to panes carrying that
category. A category with no free pane stays queued; a target that is no pane, `any`, or configured category is an error. `aiswarm status` ends with a per-category rollup (panes, idle, pending messages, open `cat:` tasks). Names may not be `any`, `mcp`, or
a pane id. Backlog tasks labelled `cat:heavy` are only dispatched to panes with that
category (all `cat:` labels required); unlabelled tasks go anywhere.

### Agent-to-agent handoff (do not stream peer panes)

Prefer short `aiswarm send` pokes + durable results in backlog + a short done-ping.
Do not attach to a peer pane. Snapshot with `aiswarm capture`; block in-process with `aiswarm wait` (polls the monitor, one line of output). TUI findings are not done.

See `backlog/docs/doc-2 - Agent-to-agent-handoff-via-send-backlog-and-ping.md` for a longer example.

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
- pane command is `shell_command`. A value that is exactly a key in `swarm/models.yaml` (`codex:heavy`) expands to that command on load. Any other string is launched as written.
- nudge metadata is under `nudge.*` (`title`, `agent`, `monitor`, `babysit`, `comms`, `tasks`)
- `comms.enabled` (defaults to `monitor`) is served by the session worker, which consumes each pane's durable log and delivers on idle
- optional top-level `tasks:` configures a task-dispatch group in that same session worker (v1 source: backlog)

Notes:

- pane IDs are derived as `W.N` (window index, pane index)
- `start` creates the tmux grid (session/windows/panes) according to the YAML.
  It is **not** safe to re-run after changing pane counts or layout on a live session
  (you'll be told to recreate the session).
- One monitor per `monitor: true` pane (started by `start`)
- `start` ensures one Python `session_worker.py` for the swarm; it multiplexes base comms/message delivery for monitored panes.
- `babysit start` enables the babysit prompt group (nudges etc.) for panes with `babysit.enabled: true`.
  It does not affect the base comms worker loop. `--for 1h` (also `30m`, `90s`, or seconds)
  auto-disables that group when the deadline passes; `babysit stop` clears any timer.
- `session_worker.py` is the one process shown in `ps` for a swarm, not one Python process per pane.
  It handles comms for every configured pane and enables babysit prompts only for panes in that group.
  `pane_worker.py` is the compatibility entrypoint.
- `tasks start` enables a **session-level group in that same worker** that lists backlog
  tasks matching `tasks.ingest` (default: `To Do` + `In Progress`), claims them, and delivers a prompt via
  the durable log to free monitored panes (tasks enabled by default; opt out with
  `nudge.tasks.enabled: false`).
- `tasks stop` / `tasks start` only toggle that group; they do not restart the shared
  worker or reload edited Python code. `tasks start --for 1h` writes a deadline into
  `tasks/enabled.json`; the session worker drops the group when it expires, and
  `tasks stop` removes the timer. Use `aiswarm worker restart` to load current
  installed or editable-source code without stopping tmux panes, agents, or monitors.
- `worker restart` preserves pane specs, enabled group flags, task assignment state,
  and the durable comms database/cursors; it validates the recorded worker process
  before terminating it.
- `start`, `babysit start`, and `tasks start` write runtime files under `/tmp/nudge-swarm/<session>/`
- runtime map: `/tmp/nudge-swarm/<session>/runtime.json` (path via `aiswarm this`)
- provider session IDs: `aiswarm sessions` (also `session-ids.json` next to the
  config and under the runtime dir). Claude and Grok are launched with
  `--session-id`; live panes are matched by PID / open files, not newest-cwd.
- `aiswarm start --resume` splices a recorded id into the pane command before mint.
  Claude and Grok get `-r <id>` (an existing `--session-id` is removed first).
  Antigravity gets `--conversation <id>`. Codex becomes `codex resume <id>` plus
  the config flags. No recorded id keeps `pane.command` (Claude and Grok still mint).
  Plain `start` always mints.
- tasks dispatcher state and enable flag: `/tmp/nudge-swarm/<session>/tasks/`
- presence state: `/tmp/nudge-swarm/presence_global.json` and `/tmp/nudge-swarm/<session>/presence_local.json`

## Human Presence (`aiswarm presence`)

Agents calibrate behavior based on whether a human is present (`IN`) or away/unattended (`OUT`).
Default auto timeout is 15 minutes (`900s`), requiring no YAML configuration to work across existing swarms.

- **`IN`**: Value human time. Ask clarifying questions, seek guidance, do not leave them waiting.
- **`OUT`**: High autonomy on routine authorized tasks. Do not pause for trivial approvals; make reasonable decisions, document choices in notes, and keep moving. Seek approval if material architecture/design decision requires it.

```bash
aiswarm presence                              # effective, local, and global presence
aiswarm presence in                           # pin current swarm to IN
aiswarm presence out                          # pin current swarm to OUT
aiswarm presence local global                 # follow global presence (default)
aiswarm presence global in|out|auto           # set or reset global presence
aiswarm presence in --for 2h                  # temporary override with auto-expiry
```

## Tasks dispatcher (backlog → free panes)

Why: fixed babysit “please continue” prompts waste tokens when real work already lives in backlog.
The orchestrator must touch backlog itself (list + claim) so agents only receive a concrete task
when free. Delivery uses the durable log so the existing idle consumer still gates tmux-send.
Uses `backlog task list|view --json` only. Do not scrape `--plain`.

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
  clear_on_claim: true            # deliver /clear to pane before sending new task claim
  clear_every: 0                  # deliver /clear every N chase nudges (0 = disabled)
  complete_statuses: [Done]       # dep gate + assignment clear; case-insensitive

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
aiswarm tasks start --for 1h   # optional; auto-stop after an hour
aiswarm tasks status
aiswarm tasks once
aiswarm tasks stop
```

Claim happens **before** log delivery (`In Progress` + assignee). Completion is **not** inferred
from pane idle — the agent (or human) marks the task Done via the backlog CLI. Local assignment
state is cleared on the next poll when status is Done.

- **`skip_assignees`:** (default `[human]`) assignees the dispatcher will **not** claim or reclaim.
  Use `-a human` to park a task for people. Empty list disables. Swarm ownership is only
  `aiswarm:<session>:<pane>` — never model names.
- **Dependency gate:** any incomplete dependency (status not in `complete_statuses`, default
  `Done`) blocks claim/chase of the parent, regardless of who owns the dep. Same predicate
  clears local assignments. Link with `backlog task edit TASK-NN --depends-on TASK-BLOCKER`.
  Cycles / missing ids still block.
- **Chase:** idle + still assigned + deps Done → short re-prompt until Done/unassign. Interval is
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

When `babysit.enabled: true` and `agent` is `claude`, `codex`, or `agy`, the
babysitter samples remaining quota every `quota_probe_secs` seconds (default 300) and
uses an exponential moving average (EMA) to pace nudge intervals so quota is spread
evenly until the provider reset. YAML `agent: antigravity` is paced as `agy`.

This EMA paces nudges. Exhaustion forecasts from sampled history are a different
EMA; see `swarm/QUOTA_TRACKING.md`.

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
make capture_antigravity DUR=60
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

The monitor deliberately reports activity, not semantic agent status: any pane
output means `working` until the quiet timeout. `grok` additionally parses OSC
terminal-title updates as a fast path — title exactly `grok` flips to `idle`
immediately — but newer grok builds can leave a task-description title (e.g.
`"TASK-123 ... - grok"`) in place after finishing instead of reverting to
`grok`, so the quiet-timeout fallback is what actually clears those panes.

## Rough edges / limitations

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

nudge is a config-driven tmux swarm: activity monitor, idle-gated log delivery, optional babysit, optional backlog dispatch. Comparisons with NTM, thurbox, dmux, Claude Squad, and others are in [docs/similar-projects.md](docs/similar-projects.md).
