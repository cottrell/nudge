---
id: TASK-14
title: >-
  Make babysit prompt group dynamically toggleable inside one worker IO loop (no
  restart on babysit start/stop)
status: In Progress
assignee: []
created_date: '2026-07-05 12:52'
updated_date: '2026-07-05 13:03'
labels:
  - nudge
  - babysit
  - swarm
  - core-logic
dependencies:
  - TASK-13
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Currently, toggling the babysit group (prompt nudges, EMA, clears, etc.) on or off requires killing the worker process and starting a new one with different argv prompts (empty strings for comms-only).

This churns the single IO loop and loses in-memory state (mu/sigma EMA, current timers, etc.).

Per user model: one IO loop; comms duties always; babysit duties as a toggleable 'event group' inside it.

Change the worker (babysit.py) to re-inspect its on-disk spec (or a babysit config) at runtime (e.g. on idle polls or when considering a nudge) and adopt/drop the babysit behavior dynamically:
- If spec now has non-empty long/short prompts (and previously didn't), initialize nudge state, send startup if appropriate, set next_nudge_at.
- If spec now has empty prompts, clear next_nudge_at, skip babysit block, etc.
- Keep fast poll + drain_comms always.

Update babysitctl apply/disable paths to just write the appropriate spec (and ensure worker exists) without always forcing stop_worker + start_worker when a loop is already running for that pane.

Update status detection if needed (it already reads the live spec).

This is follow-on to the API refactor task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A running worker loop for a pane can have its babysit behavior turned on and off by updating the spec without SIGTERM/restart (in most cases)
- [x] #2 babysit.py reads/re-evaluates prompt presence from spec (not only argv) on relevant cycles
- [x] #3 babysitctl disable_babysit (or equivalent) for an active pane updates spec and avoids unnecessary restart when possible
- [ ] #4 In-memory EMA and nudge state is preserved across a toggle where possible (or properly re-initialized)
- [ ] #5 Tests (including e2e comms and status) still pass; add coverage for toggle-without-restart if feasible
- [ ] #6 No breakage to forced nudges, clears, startup nudge, etc.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dynamic support: _current_prompts() in babysit.py re-reads spec each loop. _prompts_only_change + direct spec write in babysitctl avoids restart on toggle. Runtime map tweak as side effect for thoth issue.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-05 13:03
---
Dynamic reload and hot-update implemented + committed. Part of the same commit de3f580. Review delegated in parallel to claude/codex panes.
---
<!-- COMMENTS:END -->
