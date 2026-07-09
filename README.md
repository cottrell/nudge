# nudge

Config-driven tmux agent orchestration and monitoring.

Primary workflow is the YAML swarm CLI under `swarm/cli.py`.

States: `unknown` `working` `idle`

## Basic operational flow

```bash
# 1. Turn on the swarm (tmux session + panes + per-pane monitors + worker loops)
#    Note: this is mostly a "create" for the tmux grid. Changing pane counts later
#    requires stopping and re-starting (see limitations below).
python swarm/cli.py start ./swarm/<project>.yaml

# Architecture notes:
# - One tmux *session* per YAML file (named by `session_name`)
# - One *monitor* (activity detector via monitor-bin) per `monitor: true` pane
#   (creates a Unix socket /tmp/<session>_<W.N>.sock per pane)
# - Comms workers (log consumers that deliver on idle) are started for monitored panes
# - **Babysit (automatic nudging / prompt loops) is NOT turned on yet**
#
# Important: `start` is **not** a full declarative "update" for the tmux grid.
# If you change the number of panes/windows in the YAML after the swarm is running,
# re-running `start` will refuse and tell you to recreate the session first.
# Worker configuration (comms/babysit) and monitor setup are more forgiving on re-start.
```

```bash
# 2. Turn on babysit for panes that have `babysit.enabled: true` in the YAML
python swarm/cli.py babysit start ./swarm/<project>.yaml
```

```bash
# 3. Turn off babysit only (swarm / monitors / comms stay up)
python swarm/cli.py babysit stop ./swarm/<project>.yaml
```

```bash
# 4. Full teardown
# - stops all workers (if running)
# - kills per-pane monitors
# - tears down the tmux session
python swarm/cli.py stop ./swarm/<project>.yaml
```

## Swarm-first workflow

Create a starter config and AGENTS note:

```bash
python swarm/cli.py init <project>
```

View/edit `./swarm/<project>.yaml`.

See the **Basic operational flow** section above for the recommended sequence (`start`, `babysit start`, `babysit stop`, `stop`).

Other useful commands:

```bash
python swarm/cli.py start --skip-grid ./swarm/<project>.yaml
python swarm/cli.py status ./swarm/<project>.yaml --brief -w
python swarm/cli.py broadcast ./swarm/<project>.yaml "AGENTS.md updated; please re-read it."
python swarm/cli.py broadcast --via-log ./swarm/<project>.yaml "use durable log"
python swarm/cli.py send ./swarm/<project>.yaml 0.0 "hello via log"
python swarm/cli.py log ./swarm/<project>.yaml --pending
python swarm/cli.py clear-comms ./swarm/<project>.yaml -y
python swarm/cli.py quota ./swarm/<project>.yaml
python swarm/cli.py av-usage ./swarm/<project>.yaml
```

Note: broadcast and log-delivered messages are sent literally. Do not add synthetic sender prefixes, and keep slash commands like `/clear` unchanged.

Status/usage reliability note:

- monitor state is activity-based: any pane output means `working`; 10 seconds without output means `idle`
- output content is not classified, so agent UI text changes do not affect state detection
- quiet long-running commands can appear idle, while continuous idle-screen redraws can appear working
- `usage` is handled separately and remains best-effort; treat it as an operator hint

Attach after start if needed:

```bash
python swarm/cli.py start ./swarm/<project>.yaml --attach
```

tmuxp-first flow:

```bash
tmuxp load ./swarm/<project>.yaml
python swarm/cli.py start --skip-grid ./swarm/<project>.yaml
```

Built-in examples:

- `examples/swarm-single.yaml`
- `examples/swarm-grid.yaml`

## Config model

- one tmux session
- one or more tmux windows
- each window has `window_name`, `layout`, and `panes`
- pane command is `shell_command`
- nudge metadata is under `nudge.*` (`title`, `agent`, `monitor`, `babysit`, `comms`)
- `comms.enabled` (defaults to `monitor`) starts a per-pane worker that consumes the durable log and delivers on idle

Notes:

- pane IDs are derived as `W.N` (window index, pane index)
- `start` creates the tmux grid (session/windows/panes) according to the YAML.
  It is **not** safe to re-run after changing pane counts or layout on a live session
  (you'll be told to recreate the session).
- One monitor per `monitor: true` pane (started by `start`)
- `start` ensures the base worker loop (comms/message delivery) for monitored panes.
- `babysit start` enables the babysit prompt group (nudges etc.) for panes with `babysit.enabled: true`.
  It does not affect the base comms worker loop.
- `start` and `babysit start` write runtime files under `/tmp/nudge-swarm/<session>/`
- runtime map: `/tmp/nudge-swarm/<session>/runtime.json`
- self-awareness note: `/tmp/nudge-swarm/<session>/self-awareness.txt`

## Internal plumbing

These are low-level helpers used by swarm tooling and power users:

- `attach.sh` (monitor attach to pane)
- `tmux-send` (safe text+Enter send)

## Messaging / durable comms

Use the built-in log for reliable agent-to-agent messages (durable, replayable, with cursors):

```bash
# direct to pane via log (buffered until consumer delivers on idle)
python swarm/cli.py send ./swarm/<project>.yaml 0.2 "review this"

# broadcast via log
python swarm/cli.py broadcast --via-log ./swarm/<project>.yaml "new plan"

# inspect
python swarm/cli.py log ./swarm/<project>.yaml --pending
python swarm/cli.py cursors ./swarm/<project>.yaml
python swarm/cli.py clear-comms ./swarm/<project>.yaml -y
```

The worker loop (started automatically by `start` for `monitor: true` panes) consumes the log and delivers via `tmux-send` when the pane is idle. `babysit start` additionally enables the prompt-nudge logic on top for configured panes.

Direct/manual still works with `tmux-send`.

When messaging panes manually, prefer `tmux-send` (or the log commands) over raw `tmux send-keys`.

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

`monitor-bin` is the only monitor implementation.

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

## Similar projects

- [ccmanager](https://github.com/kbwo/ccmanager)
- [tallr](https://github.com/kaihochak/tallr)
- [agent-tmux-monitor](https://github.com/damelLP/agent-tmux-monitor)
- [tmuxcc](https://github.com/nyanko3141592/tmuxcc)
- [agent-deck](https://github.com/asheshgoplani/agent-deck)
- [agent-of-empires](https://github.com/njbrake/agent-of-empires)
- [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator)
- [tmuxp](https://tmuxp.git-pull.com/)
- [tmuxinator](https://github.com/tmuxinator/tmuxinator)
- [teamocil](https://github.com/remiprev/teamocil)
- [Zellij](https://zellij.dev/)

See `AGENTS.md` for contribution guidance and `backlog/tasks/` for planned work.
