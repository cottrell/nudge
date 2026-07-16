---
id: TASK-30
title: 'Self-awareness: prefer aiswarm instructions this over /tmp prose file'
status: Done
assignee:
  - grok
created_date: '2026-07-16 10:28'
updated_date: '2026-07-16 10:59'
labels: []
dependencies: []
references:
  - task-28
  - task-27
documentation:
  - doc-2
modified_files:
  - swarm/common.py
  - swarm/cli.py
  - swarm/instructions.py
  - swarm/topology.py
  - swarm/babysitctl.py
  - swarm/tasksctl.py
  - swarm/init.py
  - AGENTS.md
  - README.md
  - test_swarm.py
  - backlog/docs/doc-2 - Agent-to-agent-handoff-via-send-backlog-and-ping.md
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context (post TASK-25/27/28/29 + Claude review)

We now have:
- `aiswarm` bare cheat sheet
- `aiswarm instructions` (overview / handoff / tasks) — package-shipped workflow
- AGENTS.md AISWARM block — short pointer
- `/tmp/nudge-swarm/<session>/self-awareness.txt` — written on start (and some babysit/tasks paths)

Claude review (pane 0.2, session log; no done-ping received): **mostly sane**. Live /tmp file was stale (session not restarted) — expected, not the main design question.

Operator question: do we still need the /tmp *prose* dump? Can the same information live under something like `aiswarm instructions this` / `aiswarm instructions self-awareness` so agents get it from the CLI (updates with aiswarm package) instead of a second file that drifts until restart?

## What is actually dynamic vs static

**Static (belongs in package `aiswarm instructions`):**
- lifecycle, channels, handoff, tasks rules, hard rules (no raw send-keys)

**Dynamic (must come from *this* running swarm):**
- session name, resolved config path, pane ids/titles/agents
- runtime map path, monitor sockets, babysit/tasks pids
- whether session exists / workers up

Static text in the package **cannot** honestly hardcode those. Putting live paths into a shipped guide would be wrong.

## Options

| Option | Pros | Cons |
|---|---|---|
| (a) Keep /tmp self-awareness.txt as prose | `cat` one path agents already know | Second prose copy; drifts until restart; duplicates instructions |
| (b) Slim /tmp file to resolved values + 1 line pointer | Minimal drift surface | Still a write path + two sources of truth |
| (c) **Drop /tmp prose; add `aiswarm instructions this` (or `self`)** that *prints* live map by resolve_config + runtime.json | One CLI for workflow *and* "who am I"; package updates improve formatter; no stale file | Agents must run a command (not only cat); needs runtime.json still |
| (d) Only runtime.json + static instructions | Least surface | JSON unfriendly for agents; no one-glance prose map |

## Recommended direction (for next implement)

**Prefer (c), keep runtime.json under /tmp (or current runtime dir).**

- `/tmp/.../runtime.json` stays the **machine** state written on start (sockets, pids) — not a second manual.
- **Delete or stop writing** `self-awareness.txt` prose (or keep writing only if something external depends on the path — check thoth/etc.).
- New guide/command: `aiswarm instructions this` (name TBD) that:
  1. resolves config (same as other commands)
  2. reads runtime map if present
  3. prints the session-specific "who am I" block (what self-awareness used to be)
- Static `overview` says: after start, run `aiswarm instructions this` (not "read /tmp/.../self-awareness.txt").
- AGENTS block: drop hardcoded `/tmp/.../self-awareness.txt` prose path; point at `aiswarm instructions this` + optional runtime.json path pattern.

### Update / "break old swarms" concern

- Old sessions with old self-awareness.txt: harmless orphan files; agents using new CLI get live print from `instructions this`.
- Old agents taught only `cat self-awareness.txt`: AGENTS + overview must switch the pointer; one migration note.
- Package upgrade does **not** break old runtime.json schema if `instructions this` is defensive (missing keys → clear message "start the swarm first").
- Putting *dynamic* data into static package instructions would be worse than /tmp drift.

## Claude also suggested (optional)

- Regen self-awareness on status/send if keeping (b) — moot if (c).
- Did not send done-ping to requester pane (TASK-25 dogfood gap: pattern not yet muscle memory / no new self-awareness on unrestarted swarm).

## Out of scope for this task until chosen

- Implement (c) without explicit go-ahead
- Renaming /tmp/nudge-swarm prefix
- Restart of live nudge swarm (operator may restart after this note lands)

## Acceptance when implementing

- [ ] Decision recorded (c vs b) in this task or a decision doc
- [ ] If (c): `aiswarm instructions this` (or agreed name) prints live session map; overview/AGENTS/init updated; self-awareness.txt write removed or deprecated with note
- [ ] Tests for the command with/without runtime present
- [ ] No second full workflow manual reintroduced
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Record design choice: drop /tmp prose in favor of live CLI dump vs slim file
- [x] #2 If implementing CLI path: instructions this (or name) uses resolve_config + runtime.json
- [x] #3 Static overview/AGENTS no longer teach cat self-awareness.txt as primary
- [x] #4 runtime.json remains machine state; do not put dynamic session values in package-static guide text
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decision: keep runtime.json on disk; stop self-awareness.txt; add aiswarm this as identity pointer only (no enrichment).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision (2026-07-16):

1. Keep /tmp/.../runtime.json as machine map (targets, sockets, sibling pids/paths). Tools/UIs/scripts need a file.
2. Stop writing and teaching self-awareness.txt prose (duplicates instructions; drifts).
3. Add aiswarm this: resolve config, print session + config path + runtime.json path (+ present/missing) + pane ids. No status enrichment, no second manual.
4. Workflow stays in aiswarm instructions overview/handoff/tasks.

Implemented: build_this_text + aiswarm this; removed write_self_awareness_text call sites; AGENTS/init/overview/README/doc-2 updated; tests green.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Kept runtime.json as the on-disk machine map. Dropped self-awareness.txt write path. Added aiswarm this (session, config path, runtime.json location + present/missing, pane ids). Docs/AGENTS/overview point at it; no enrichment beyond path identity. 46 tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
