# monitor

Minimal agent nudging system. Reads a tmux pane stream, classifies agent state,
serves it over a Unix socket, and nudges the agent when idle.
States: `unknown` `working` `idle` `rate_limited` `error`

**User-facing scripts:**
- `launch.sh <session> <agent>` — create session if needed, attach monitor, drop into tmux
- `babysit.sh <session>` — poll state, nudge on idle, back off on rate_limited

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

```bash
# start agent
tmux new-session -d -s claude_myproject_alice
tmux send-keys -t claude_myproject_alice "claude --dangerously-skip-permissions" Enter

# attach monitor
./attach.sh claude_myproject_alice claude

# query
echo status | nc -U /tmp/claude_myproject_alice.sock  # {"state": "working"}
echo log    | nc -U /tmp/claude_myproject_alice.sock  # {"log": [...]}
echo tail   | nc -U /tmp/claude_myproject_alice.sock  # {"line": "..."}
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
