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

1. **Understand the codebase** — Read `README.md` and existing patterns in `monitor.py` / `monitor.c`
2. **Make changes** — Edit the relevant files (both Python and C for pattern changes)
3. **Run tests** — `make test` (Python) and `make test-c` (C + fixture replay)
4. **Commit** — Use clear, descriptive commit messages

## Pattern Changes

When adding or modifying agent patterns:
- Update **both** `monitor.py` (PATTERNS dict) and `monitor.c` (PATS array)
- Keep patterns in sync between Python and C
- Add tests for new patterns in `test_monitor.py`
- Update help text in `launch.sh`, `attach.sh`, `capture_fixture.sh`, `Makefile`

## Backend Status

- **C (`monitor-bin`)** — Primary runtime, default backend, production use
- **Python (`monitor.py`)** — Reference implementation, test coverage, debug use

The Python version is maintained for testing and as the specification reference, but the C binary is the intended production backend.

## Questions?

If unsure about a change, err on the side of making it — the test suite provides good coverage, and the codebase is small enough that mistakes are easy to spot and fix.
