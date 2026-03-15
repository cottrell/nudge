# Agent Development Guidelines

This repository welcomes contributions from AI agents. Unlike most projects, **it is acceptable and expected that agents will commit their own work here**.

## Why This Repo Is Different

The nudge project is a toolbox for running and monitoring AI coding agents (claude, codex, copilot, gemini, vibe, qwen) in tmux. The codebase is intentionally small and stable:

- **Single C binary** (`monitor.c` → `monitor-bin`) with no external dependencies
- **Shell scripts** for tmux orchestration
- **Python tests** (`test_monitor.py`) for validation

This simplicity makes it safe for agents to modify — there's minimal risk of breaking complex abstractions or introducing subtle bugs.

## When to Commit

You should commit your work when:
- Adding support for a new agent (new patterns, updated help text, tests)
- Fixing bugs in the monitor or shell scripts
- Improving tests or capture fixtures
- Updating documentation (README, TODO, this file)

## Development Workflow

1. **Understand the codebase** — Read `README.md` and existing patterns in `monitor.c`
2. **Make changes** — Edit `monitor.c` for pattern/logic changes
3. **Run tests** — `make test` (Python) and `make test-c` (C + fixture replay)
4. **Commit** — Use clear, descriptive commit messages

## Backend Status

- **C (`monitor.c` / `monitor-bin`)** — **Production backend**, fast, no dependencies
- **Python (`monitor.py`)** — **Test oracle / reference implementation**

**Agents should implement all changes in C.** The Python version serves two purposes:

1. **Reference** — Shows intended behavior in a more readable form
2. **Test validation** — `test_fixture_replay_c_matches_python_final_state` verifies C matches Python

**Keep Python in sync for pattern changes** so the test oracle remains accurate. If Python drifts, the fixture replay tests may fail or become meaningless.

## Pattern Changes

When adding or modifying agent patterns:
- **Implement in C first** (`monitor.c` PATS array)
- **Also update Python** (`monitor.py` PATTERNS dict) — keeps test oracle accurate
- Add tests for new patterns in `test_monitor.py`
- Update help text in `examples/launch-single-pane.sh`, `attach.sh`, `capture_fixture.sh`, `Makefile`

## Questions?

If unsure about a change, err on the side of making it — the test suite provides good coverage, and the codebase is small enough that mistakes are easy to spot and fix.
