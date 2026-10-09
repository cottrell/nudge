# Agent Development Guidelines

Agents commit their own work in this repo.

## Shape

- Toolbox for claude, codex, copilot, gemini, grok, vibe, qwen, antigravity in tmux.
- `monitor.c` → `monitor-bin`. Only monitor. No extra deps.
- Shell: `attach.sh`, `tmux-send`.
- Python package: `swarm/`. Workers `session_worker.py` and `pane_worker.py` stay at the repo root.
- Tests: `make test`.

## State

- Do not keep project state in chat memory.
- Keep it in backlog tasks or project memory files.
- Re-read those and run `aiswarm this` when you need swarm paths.
- Babysit sends `/clear` only when `clear_every` is set. Weight profiles set it. Default is 0.
- After `/clear`, babysit re-sends `long_prompt`.

## Monitor

- Any pane output is `working`. Quiet timeout → `idle`.
- One exception: a grok OSC title of exactly `grok` goes `idle` immediately. A leftover task title stays `working` until the quiet timeout.
- Do not add more agent UI patterns unless that design changes.
- State changes: C first, then `test_monitor.py`, then help text.

## Commit when

- New agent support, monitor or shell fixes, tests, capture fixtures, docs.

## Workflow

- Read `README.md` and `monitor.c` before state changes.
- `make test` before commit.

<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.51.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**When you are dealing with backlog tasks, run `backlog instructions overview` before answering or taking action. Re-read it only if you have not read it yet in the current conversation.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->

<!-- AISWARM/NUDGE GUIDELINES START -->
## Swarm

Swarm CLI: `aiswarm` (on PATH; `make install-aiswarm` from the nudge repo).

Read workflow first:
- `aiswarm` — common commands cheat sheet
- `aiswarm instructions overview` — required agent briefing
- `aiswarm instructions tasks` — backlog dispatcher
- `aiswarm instructions presence` — human availability & autonomy guidance
- `aiswarm this` — this swarm's config + runtime.json path

After start, machine map (not git): `/tmp/nudge-swarm/nudge/runtime.json`

Config: `.aiswarm/config.yaml` (cwd walk-up), `$AISWARM_CONFIG`, or explicit path.
Messaging: `aiswarm send <pane> "msg"` (durable log). Do NOT raw `tmux send-keys`.
Do NOT attach/stream a peer pane. Snapshot: `aiswarm capture`. Block until idle: `aiswarm wait`.
Human presence: `aiswarm presence` (`IN` -> ask questions; `OUT` -> autonomous progress on routine authorized tasks, do not pause for trivial approvals; seek approval if material architecture/design decision requires it).
TUI findings are not done: file backlog tasks/docs, ping the requester, then idle.
<!-- AISWARM/NUDGE GUIDELINES END -->
