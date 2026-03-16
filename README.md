# nudge

Composable tmux agent tools. The scripts are meant to be used together, but
each piece is also useful on its own. The repo currently covers three related
jobs:

- monitor an agent pane and classify its state
- query that state over a Unix socket
- drive the session safely, either with automatic nudges or a split-pane input path

States: `unknown` `working` `idle` `rate_limited` `error`

**User-facing scripts:**
- `attach.sh <session-or-target> <agent>` — attach the monitor to an existing session or pane target
- `babysit.sh <session>` — poll state, nudge on idle, wait on unknown/rate_limited
- `keyboard-2pane.sh [target-pane]` — relay typed lines to another pane without prompt clobbering
- `tmux-send <target> <text...>` — send literal text plus Enter to a pane
  When run from inside tmux, it prefixes the message with the sender pane target in `session:window.pane` form.

**Examples:**
- `examples/launch-single-pane.sh <session> <agent>` — create or resume a monitored single-pane session
- `examples/launch-2pane.sh <session> <agent> [command]` — create a monitored split-pane session with a dedicated input pane
- `examples/launch-agent-grid.sh [session] [window]` — six-pane mixed-agent grid example using explicit pane monitors
- `examples/swarm-single.yaml` — minimal declarative single-agent config
- `examples/swarm-grid.yaml` — declarative grid config for the experimental Python swarm apply tools

The repo name still fits if you think of "nudge" as the original behavior plus
the surrounding operator tools, but the project is better described as a small
toolbox than a single-purpose nudger.

No colons in tmux session names — use underscores.

`send-keys` requires `C-m` (Enter) as a **separate call** — combining text and `C-m` in one call does not submit:
```bash
tmux send-keys -t mysession:0.0 -l -- "some text"
sleep 0.1
tmux send-keys -t mysession:0.0 C-m
```

One session per agent, one window, one pane. `pipe-pane` and `send-keys` target
`session:window.pane` — with a single pane the session name alone is unambiguous.
For multiple panes you must be explicit: `claude_myproject_alice:0.0`.

## Monitored sessions

```bash
# create or resume a monitored session and attach to it
./examples/launch-single-pane.sh claude_myproject_alice claude

# start the agent inside tmux if the session is new
tmux send-keys -t claude_myproject_alice:0.0 -l -- "claude --dangerously-skip-permissions"
sleep 0.1
tmux send-keys -t claude_myproject_alice:0.0 C-m

# query the monitor socket
echo status | nc -U /tmp/claude_myproject_alice.sock  # {"state": "working"}
echo log    | nc -U /tmp/claude_myproject_alice.sock  # {"log": [...]}
echo tail   | nc -U /tmp/claude_myproject_alice.sock  # {"line": "..."}
```

You can also create the tmux session yourself and then run:

```bash
./attach.sh claude_myproject_alice claude
./attach.sh claude_myproject_alice:0.0 claude
```

```bash
make build      # compile C binary (default backend)
make test       # C smoke + fixture replay parity check
make test-python # Python unit tests (optional, may be out of sync)
make test-c     # Same as 'make test'
make test-swarm # Swarm config/apply unit tests
make capture AGENT=claude DUR=60  # real tmux capture -> fixtures/claude_capture.txt
make capture_claude DUR=60
make capture_codex DUR=60
make capture_copilot DUR=60
make capture_gemini DUR=60
make capture_vibe DUR=60
make capture_qwen DUR=60
make capture_all DUR=60
make tmux-test  # manual test with a plain session, no agent needed
```

Python helpers and swarm scripts are now declared in `pyproject.toml`.
If you want the project environment explicitly:

```bash
uv sync
```

`attach.sh` uses the C binary by default. Set `MONITOR_BACKEND=python` to use the Python version instead.

## Backend status

- **C (`monitor-bin`)** — Production runtime, fast, no dependencies
- **Python (`monitor.py`)** — Reference implementation and test oracle

The Python version defines expected behavior. The C binary must match Python's output — this is verified by `make test` which runs fixture replay tests comparing both implementations. See [AGENTS.md](AGENTS.md) for development guidelines.

Debug helpers for either backend:

```bash
MONITOR_DEBUG=1 ./attach.sh mysession claude
MONITOR_STATE_LOG=1 ./attach.sh mysession claude
MONITOR_DEBUG=1 MONITOR_STATE_LOG=1 ./examples/launch-2pane.sh mysession gemini
```

Defaults:
- `MONITOR_DEBUG=1` writes raw ingested lines to `/tmp/<session>.raw`
- `MONITOR_STATE_LOG=1` writes init/state-change events to `/tmp/<session>.state.log`

Capture fixtures are repr-encoded raw pane lines from the monitor's ingest stream, scrubbed for common sensitive tokens. Capture also writes exact state transitions to `fixtures/<agent>_transitions.jsonl`. They are intended to be committed and replayed in tests. Re-capture only when agent output format or classifier behavior changes.

Current note: fixture replay currently covers `claude`, `codex`, `copilot`, `gemini`, and `qwen`. `vibe` still has unit/integration coverage in the test suite, but its committed live fixture is intentionally paused until the upstream service is responsive enough to complete a clean `say hello -> idle` capture.

What went wrong: the earlier tests were incomplete, not wholly wrong. They replayed raw captures, but they were too permissive about transition fixtures, and they missed live tmux behaviors where an agent could redraw an idle-looking prompt during active work or settle visually to idle without emitting a fresh idle line. The monitor now handles both cases, and the tests are stricter about transition fixtures for the agents with committed captures.

## Swarm Config

There is now an experimental config-driven orchestration path under `swarm/`:

```bash
python swarm/apply.py examples/swarm-single.yaml --dry-run
python swarm/apply.py examples/swarm-grid.yaml --dry-run
python swarm/apply.py examples/swarm-grid.yaml status
python swarm/apply.py examples/swarm-grid.yaml status --brief
python swarm/apply.py examples/swarm-grid.yaml status --brief --watch
python swarm/babysit_apply.py examples/swarm-grid.yaml apply --dry-run
python swarm/babysit_apply.py examples/swarm-grid.yaml status
cat /tmp/nudge-swarm/agent_grid/runtime.json
cat /tmp/nudge-swarm/agent_grid/self-awareness.txt
```

The current config model is:
- one tmux session
- one tmux window
- explicit `layout.rows` and `layout.cols`
- explicit pane list with `pane`, optional `title`, `agent`, `command`, `monitor`, and optional `babysit`
- `babysit.long_prompt_file` / `babysit.long_prompt` for the initial full babysit send
- optional `babysit.short_prompt_file` / `babysit.short_prompt` for later idle reminders

Important current limitation:
- `rows` and `cols` are mandatory and validated, but v1 still realizes the grid by creating the requested pane count and then applying tmux `select-layout tiled`
- so the config expresses the intended grid shape, but tmux still controls the exact final geometry

The split between the two entry points is deliberate:
- `swarm/apply.py` reconciles tmux topology, monitors, and initial pane commands
- `swarm/babysit_apply.py` reconciles babysit workers from the same YAML config

The intent is to replace ad hoc shell orchestration like `babysit-manager.sh` with short-lived, idempotent Python apply steps.

Runtime notes:
- babysit worker pid/spec/log files live under `/tmp/nudge-swarm/<session>/`
- `swarm/apply.py` and `swarm/babysit_apply.py` write a derived runtime map to `/tmp/nudge-swarm/<session>/runtime.json`
- they also write `/tmp/nudge-swarm/<session>/self-awareness.txt`, a short copy-pastable note with the runtime map path plus status/watch commands you can reference in prompts or `AGENTS.md`
- `make test` now includes `test_swarm.py`, which validates config loading and apply/babysit reconciliation logic without needing live tmux agents
- `swarm/apply.py ... status --watch` redraws in place; use `--brief` for a compact per-pane state view and `--interval` to change the default 1s refresh cadence
- `title` sets the tmux pane title and the initial shell prompt prefix; if omitted it defaults to the `agent` name or the pane id, and some agent CLIs may later overwrite the terminal title themselves
- babysit sends the long prompt once when the worker starts, then uses the short prompt for later idle nudges; if no short prompt is configured it falls back to the long prompt
- the runtime map is written unconditionally as an operator/runtime artifact, but it is not auto-injected into agent prompts; if you want agents to coordinate or inspect each other, mention the runtime map path explicitly in your long or short babysit prompt

To add an agent: add a key to `PATTERNS` in `monitor.py`.

## Two-pane interaction

For a monitored split-pane setup where your typing happens in a dedicated input
pane, use `examples/launch-2pane.sh`:

```bash
# top pane: agent or shell, monitored on :0.0
# bottom pane: input relay on :0.1
./examples/launch-2pane.sh mychat codex
```

This creates one tmux window with:
- top pane running the command you passed
- bottom pane running `keyboard-2pane.sh`, which forwards each submitted line to the pane above

To send text from another terminal:
```bash
./tmux-send mychat "Hello agent"
```

`tmux-send` defaults a bare session name like `mychat` to `mychat:0.0`, which
matches the top pane created by `examples/launch-2pane.sh`.

## Similar projects

- [ccmanager](https://github.com/kbwo/ccmanager) — Go TUI, supports Claude/Gemini/Codex/Cursor/etc, state detection; missing the small socket-first/no-TUI control surface used here
- [tallr](https://github.com/kaihochak/tallr) — desktop dashboard, real-time state detection + native notifications; missing tmux-native babysit/control loops
- [agent-tmux-monitor](https://github.com/damelLP/agent-tmux-monitor) — uses Claude Code hooks rather than pipe-pane, TUI dashboard; less useful if you want hook-free multi-agent monitoring across CLIs
- [tmuxcc](https://github.com/nyanko3141592/tmuxcc) — TUI dashboard for the same agent set; missing the scriptable socket/CLI orchestration angle
- [agent-deck](https://github.com/asheshgoplani/agent-deck) — full session manager with state detection and MCP management; heavier and less minimal than this repo’s shell/C/Python toolbox
- [agent-of-empires](https://github.com/njbrake/agent-of-empires) — Rust, tmux + git worktrees, parallel agents; more opinionated around worktrees/session management than simple monitoring + nudging
- [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator) — tmux plugin for visual state feedback (running/needs-input/done); missing process control, sockets, and babysit behavior
- [tmuxp](https://tmuxp.git-pull.com/) — declarative tmux session manager with YAML/JSON configs; missing agent-state monitoring and babysit semantics
- [tmuxinator](https://github.com/tmuxinator/tmuxinator) — declarative tmux project/session launcher; missing monitor/socket integration and agent-specific state handling
- [teamocil](https://github.com/remiprev/teamocil) — YAML tmux session layout manager; missing monitoring and reconciliation logic for agent panes
- [Zellij](https://zellij.dev/) — alternative terminal multiplexer with built-in layout/config support; would require rebuilding the tmux-specific `pipe-pane`/`send-keys` model
- [Agent Hand (HN)](https://news.ycombinator.com/item?id=47192207) — Rust, TTL-based idle detection; narrower than this repo’s monitor + orchestration + babysit toolset
- [Adventures in Babysitting Coding Agents (HN)](https://news.ycombinator.com/item?id=44205137) — useful background/motivation, but not an operator tool you can run directly

This project's angle: no-TUI, socket-first IPC queryable with `nc`, C binary with no runtime deps, babysit loop as first-class feature.

For now, tmux remains the primary substrate here because `pipe-pane`, `send-keys`, and pane-target naming are the core control primitives the monitor and babysit loops already rely on. A useful later experiment would be to ask agents to re-implement the same config-driven topology/orchestration layer on top of `tmuxp`, `tmuxinator`, or `zellij` and compare complexity, reliability, and operator ergonomics.

## Community patterns

Multi-agent tmux setups in the wild typically use:
- **One session per agent** — Clean isolation, matches this project's design
- **Pane grids** — Now supported via `session:window.pane` socket naming
- **Two-step send-keys** — Text then `C-m` separately (all scripts here do this)

See [AGENTS.md](AGENTS.md) for development guidelines and [TODO.md](TODO.md) for planned enhancements like config-driven orchestration.
