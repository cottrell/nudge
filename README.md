# nudge

Composable tmux agent tools. The scripts are meant to be used together, but
each piece is also useful on its own. The repo currently covers three related
jobs:

- monitor an agent pane and classify its state
- query that state over a Unix socket
- drive the session safely, either with automatic nudges or a split-pane input path

States: `unknown` `working` `idle` `rate_limited` `error`

**User-facing scripts:**
- `launch.sh <session> <agent>` — create or resume a monitored single-pane session
- `attach.sh <session> <agent>` — attach the monitor to an existing session
- `babysit.sh <session>` — poll state, nudge on idle, back off on rate_limited
- `safe-launcher.sh <session> [command]` — create a split-pane session with a dedicated input pane
- `safe-keyboard.sh [target-pane]` — relay typed lines to another pane without prompt clobbering
- `tmux-send <target> <text...>` — send literal text plus Enter to a pane

The repo name still fits if you think of "nudge" as the original behavior plus
the surrounding operator tools, but the project is better described as a small
toolbox than a single-purpose nudger.

No colons in tmux session names — use underscores.

`send-keys` requires `C-m` (Enter) as a **separate call** — combining text and `C-m` in one call does not submit:
```bash
tmux send-keys -t mysession "some text"
sleep 0.1
tmux send-keys -t mysession C-m
```

One session per agent, one window, one pane. `pipe-pane` and `send-keys` target
`session:window.pane` — with a single pane the session name alone is unambiguous.
For multiple panes you must be explicit: `claude_myproject_alice:0.0`.

## Monitored sessions

```bash
# create or resume a monitored session and attach to it
./launch.sh claude_myproject_alice claude

# start the agent inside tmux if the session is new
tmux send-keys -t claude_myproject_alice "claude --dangerously-skip-permissions"
sleep 0.1
tmux send-keys -t claude_myproject_alice C-m

# query the monitor socket
echo status | nc -U /tmp/claude_myproject_alice.sock  # {"state": "working"}
echo log    | nc -U /tmp/claude_myproject_alice.sock  # {"log": [...]}
echo tail   | nc -U /tmp/claude_myproject_alice.sock  # {"line": "..."}
```

You can also create the tmux session yourself and then run:

```bash
./attach.sh claude_myproject_alice claude
```

```bash
make build      # compile C binary (default backend)
make test       # Python unit tests
make test-c     # C smoke + fixture replay parity check vs Python
make capture AGENT=claude DUR=60  # real tmux capture -> fixtures/claude_capture.txt
make capture_claude DUR=60
make capture_codex DUR=60
make capture_copilot DUR=60
make capture_gemini DUR=60
make capture_vibe DUR=60
make capture_all DUR=60
make tmux-test  # manual test with a plain session, no agent needed
```

`attach.sh` uses the C binary by default. Set `MONITOR_BACKEND=python` to use the Python version instead.

Capture fixtures are repr-encoded raw pane lines, scrubbed for common sensitive tokens. They are intended to be committed and replayed in tests. Re-capture only when agent output format or classifier behavior changes.

To add an agent: add a key to `PATTERNS` in `monitor.py`.

## Safe interaction

For a split-pane setup where your typing happens in a dedicated input pane, use
`safe-launcher.sh`:

```bash
# top pane: agent or shell
# bottom pane: safe input relay
./safe-launcher.sh mychat codex
```

This creates one tmux window with:
- top pane running the command you passed
- bottom pane running `safe-keyboard.sh`, which forwards each submitted line to the pane above

To send text from another terminal:
```bash
./tmux-send mychat "Hello agent"
```

`tmux-send` defaults a bare session name like `mychat` to `mychat:0.0`, which
matches the top pane created by `safe-launcher.sh`.

## Similar projects

- [ccmanager](https://github.com/kbwo/ccmanager) — Go TUI, supports Claude/Gemini/Codex/Cursor/etc, state detection
- [tallr](https://github.com/kaihochak/tallr) — desktop dashboard, real-time state detection + native notifications
- [agent-tmux-monitor](https://github.com/damelLP/agent-tmux-monitor) — uses Claude Code hooks rather than pipe-pane, TUI dashboard
- [tmuxcc](https://github.com/nyanko3141592/tmuxcc) — TUI dashboard for the same agent set
- [agent-deck](https://github.com/asheshgoplani/agent-deck) — full session manager with state detection and MCP management
- [agent-of-empires](https://github.com/njbrake/agent-of-empires) — Rust, tmux + git worktrees, parallel agents
- [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator) — tmux plugin for visual state feedback (running/needs-input/done)
- [Agent Hand (HN)](https://news.ycombinator.com/item?id=47192207) — Rust, TTL-based idle detection
- [Adventures in Babysitting Coding Agents (HN)](https://news.ycombinator.com/item?id=44205137)

This project's angle: no-TUI, socket-first IPC queryable with `nc`, C binary with no runtime deps, babysit loop as first-class feature.
