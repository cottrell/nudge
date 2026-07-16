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
- **DO** re-read backlog / project memory and run `aiswarm this` when you need swarm paths.

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

## Questions?

If unsure about a change, err on the side of making it — the test suite provides good coverage, and the codebase is small enough that mistakes are easy to spot and fix.

<!-- AISWARM/NUDGE GUIDELINES START -->
## Swarm

Swarm CLI: `aiswarm` (on PATH; `make install-aiswarm` from the nudge repo).

Read workflow first:
- `aiswarm` — common commands cheat sheet
- `aiswarm instructions overview` — required agent briefing
- `aiswarm instructions handoff` / `tasks` — peer send and backlog dispatch
- `aiswarm this` — this swarm's config + runtime.json path

After start, machine map (not git): `/tmp/nudge-swarm/nudge/runtime.json`

Config: `.aiswarm/config.yaml` (cwd walk-up), `$AISWARM_CONFIG`, or explicit path.
Messaging: `aiswarm send <pane> "msg"` (durable log). Do NOT raw `tmux send-keys`.
<!-- AISWARM/NUDGE GUIDELINES END -->

<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.48.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**For every user request in this project, run `backlog instructions overview` before answering or taking action.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->
