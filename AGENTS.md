# Agent Development Guidelines

This repository welcomes contributions from AI agents. Unlike most projects, **it is acceptable and expected that agents will commit their own work here**.

## Why This Repo Is Different

The nudge project is a toolbox for running and monitoring AI coding agents (claude, codex, copilot, gemini, vibe, qwen) in tmux. The codebase is intentionally small and stable:

- **Single C binary** (`monitor.c` → `monitor-bin`) with no external dependencies
- **Shell scripts** for tmux orchestration
- **Python tests** (`test_monitor.py`) for validation

This simplicity makes it safe for agents to modify — there's minimal risk of breaking complex abstractions or introducing subtle bugs.

## Statelessness & File-based Memory

Agents in this swarm should be designed to be **stateless**. The babysit loop periodically issues a `/clear` command to the agent to manage token costs and context length.

Because conversation history is regularly wiped:
- **Do NOT** rely on the agent's memory of past turns for project state.
- **DO** maintain all critical state (tasks, progress, architectural decisions) in files like `TODO.md`, `GEMINI.md`, or project-specific memory files.
- **DO** read relevant context files (like the `self-awareness.txt` note) whenever you start a new task.

The babysit loop will re-issue the full project briefing (`long_prompt`) immediately after every `/clear` to restore the agent's awareness of its environment and mission.

## When to Commit

You should commit your work when:
- Adding support for a new agent (validation, help text, tests)
- Fixing bugs in the monitor or shell scripts
- Improving tests or capture fixtures
- Updating documentation (README, TODO, this file)

## Development Workflow

1. **Understand the codebase** — Read `README.md` and the activity logic in `monitor.c`
2. **Make changes** — Edit `monitor.c` for state logic changes
3. **Run tests** — `make test` (Python) and `make test-c` (C + fixture replay)
4. **Commit** — Use clear, descriptive commit messages

## Backend Status

- **C (`monitor.c` / `monitor-bin`)** — **Production backend**, fast, no dependencies
- **Python (`monitor.py`)** — **Test oracle / reference implementation**

**Agents should implement all changes in C.** The Python version serves two purposes:

1. **Reference** — Shows intended behavior in a more readable form
2. **Test validation** — `test_fixture_replay_c_matches_python_final_state` verifies C matches Python

**Keep Python in sync for state changes** so the test oracle remains accurate.

## State Changes

The monitor is content-agnostic: any pane output is `working`, followed by `idle`
after a quiet timeout. Do not add agent UI patterns without changing that design
explicitly.

When modifying state behavior:
- Implement in C first
- Update Python to keep the test oracle accurate
- Add tests in `test_monitor.py`
- Update relevant help text and docs

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

Messaging another tmux pane: ALWAYS use `tmux-send`.
Do NOT use raw `tmux send-keys ... Enter`.

Required form:
- `/home/cottrell/dev/nudge/tmux-send <target> "message"`

Reason:
- raw `tmux send-keys ... Enter` often fails to submit Enter
- prompts can sit unexecuted until next nudge or manual Enter

Swarm scripts: `/home/cottrell/dev/nudge/swarm`.
