# Agent Development Guidelines

This repository welcomes contributions from AI agents. Unlike most projects, **it is acceptable and expected that agents will commit their own work here**.

## Why This Repo Is Different

The nudge project is a toolbox for running and monitoring AI coding agents
(claude, codex, copilot, gemini, grok, vibe, qwen, antigravity) in tmux.
The codebase is intentionally small and stable:

- **Single C binary** (`monitor.c` → `monitor-bin`) with no external dependencies
- **Shell scripts** for tmux orchestration
- **Python tests** (`test_monitor.py`) for validation

This simplicity makes it safe for agents to modify — there's minimal risk of breaking complex abstractions or introducing subtle bugs.

## Statelessness & File-based Memory

Agents in this swarm should be designed to be **stateless**. The babysit loop periodically issues a `/clear` command to the agent to manage token costs and context length.

Because conversation history is regularly wiped:
- **Do NOT** rely on the agent's memory of past turns for project state.
- **DO** maintain critical state in backlog tasks or project-specific memory files.
- **DO** read relevant context files (like the `self-awareness.txt` note) whenever you start a new task.

The babysit loop will re-issue the full project briefing (`long_prompt`) immediately after every `/clear` to restore the agent's awareness of its environment and mission.

## When to Commit

You should commit your work when:
- Adding support for a new agent (validation, help text, tests)
- Fixing bugs in the monitor or shell scripts
- Improving tests or capture fixtures
- Updating documentation (README, AGENTS, backlog docs)

## Development Workflow

1. **Understand the codebase** — Read `README.md` and the activity logic in `monitor.c`
2. **Make changes** — Edit `monitor.c` for state logic changes
3. **Run tests** — `make test`
4. **Commit** — Use clear, descriptive commit messages

## Backend Status

`monitor.c` / `monitor-bin` is the only monitor implementation.

## State Changes

The monitor is content-agnostic: any pane output is `working`, followed by `idle`
after a quiet timeout. Do not add agent UI patterns without changing that design
explicitly.

When modifying state behavior:
- Implement in C first
- Add tests in `test_monitor.py`
- Update relevant help text and docs

## Backlog

Use Backlog.md as the source of truth for planned work:
- Read with `backlog task list --plain`, `backlog task <id> --plain`, and `backlog search "<query>" --plain`
- Create or modify tasks only through the `backlog` CLI
- Do not edit files under `backlog/tasks/` directly
- Keep task notes concise; use `backlog --help` for command details

## Questions?

If unsure about a change, err on the side of making it — the test suite provides good coverage, and the codebase is small enough that mistakes are easy to spot and fix.

## Swarm

Swarm workflow: read first:
- Runtime map: `/tmp/nudge-swarm/nudge/runtime.json`
- Self-awareness note: `/tmp/nudge-swarm/nudge/self-awareness.txt`

Use as source of truth for:
- tmux pane targets
- monitor sockets, live state
- babysit pid/log/spec/state files

Messaging (durable, preferred):
- Prereq: `aiswarm` must be on `PATH`; install it with `make install-aiswarm`.
- Use the comms log for reliability between agents: `aiswarm send <cfg> <pane> "msg"` or `log_broadcast`.
- Inspect: `aiswarm log <cfg> [--pending] [--pane X.Y]`, `aiswarm cursors <cfg>`.
- Direct/manual still works: `./tmux-send <target> "message"`.

Do NOT use raw `tmux send-keys ... Enter` (fails to submit reliably).

Swarm scripts: `swarm/`.
