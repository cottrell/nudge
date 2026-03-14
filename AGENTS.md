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

- **C (`monitor.c` / `monitor-bin`)** — **Primary backend**, production use, no dependencies
- **Python (`monitor.py`)** — Reference/debug only, may be out of sync with C

**Agents should target C for all changes.** The Python version is kept for:
- Historical reference
- Occasional debugging if behavior is unclear
- Quick pattern prototyping (optional)

**Do not feel obligated to keep Python and C in sync.** Divergence is acceptable. If Python becomes useful again, it can be updated; if not, it may eventually be removed.

## Pattern Changes

When adding or modifying agent patterns:
- **Primary target:** `monitor.c` (PATS array)
- **Optional:** `monitor.py` (PATTERNS dict) — only if you want to keep them aligned
- Add tests for new patterns in `test_monitor.py`
- Update help text in `launch.sh`, `attach.sh`, `capture_fixture.sh`, `Makefile`

## Questions?

If unsure about a change, err on the side of making it — the test suite provides good coverage, and the codebase is small enough that mistakes are easy to spot and fix.
