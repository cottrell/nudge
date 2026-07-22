---
id: TASK-31
title: 'Document aiswarm tasks dispatch: one-per-free-pane, not dump-all'
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-22 08:48'
updated_date: '2026-07-22 13:59'
labels: []
dependencies: []
priority: high
type: docs
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

Operators/humans (and agents) are unclear whether `aiswarm tasks` dumps every To Do at once or stops when panes are full. Document the real policy so people do not assume flood-fill.

## Current behaviour (source of truth: swarm/tasksctl.py dispatch_once)

Per poll / `tasks once` pass:

1. **Reconcile** local assignments: drop panes whose backlog task is Done.
2. **Free panes only** — a pane is free if:
   - not in local `assignments`
   - no pending comms-log events
   - idle (if `require_idle: true`, default) or monitor unknown
3. **List candidates** from backlog (`tasks.ingest`, default `To Do` only; `unassigned_only` default true; priority sort HIGH→LOW then TASK-id).
4. **Assign at most one task per free pane** in that pass (pair free pane ↔ next candidate).
5. **Stop early** if:
   - no free panes, or
   - no candidates left, or
   - `max_inflight` > 0 and inflight assignments already at cap (0 = unlimited, still one task per pane)
6. For each assignment: **claim first** (status In Progress + assignee `aiswarm:<session>:<pane>`), then deliver prompt via durable log (or direct if `via_log: false`).
7. Long-running `tasks start` loops: sleep `poll_secs` (default 60), repeat. When a pane finishes (Done + reconcile), next poll can fill that slot only.

### Not what it does

- Does **not** dump the whole To Do list onto one pane.
- Does **not** queue multiple tasks into the same pane while one is still assigned.
- Does **not** start the dispatcher from `aiswarm start` alone — must `aiswarm tasks start` / `once`.

### Config knobs

- Pane eligibility: monitored panes default `tasks_enabled`; opt out `nudge.tasks.enabled: false`
- `tasks.ingest`, `poll_secs`, `unassigned_only`, `require_idle`, `max_inflight`, `via_log`
- Dry-run: `aiswarm tasks once -D` prints effective config + planned claims

## Outcome

Human-readable docs (README + `aiswarm instructions tasks`) state this policy in plain language with a small example (e.g. 3 free panes + 10 To Dos → claim 3 this pass; rest wait).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README tasks section states: one task per free pane per pass; remaining To Dos wait for next free slot / poll
- [x] #2 aiswarm instructions tasks states the same policy + free-pane definition + max_inflight
- [x] #3 Explicit non-goals: no dump-all, no multi-task queue per pane while assigned
- [x] #4 Example: N free panes, M candidates → min(N,M) claims this pass (respect max_inflight)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a plain-language dispatch-pass policy and N/M example to the README task dispatcher section.
2. Expand `aiswarm instructions tasks` with the same policy, free-pane eligibility, cap behavior, and non-goals.
3. Inspect the final docs against each acceptance criterion and record verification notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.0 (session nudge).

Documented one-per-free-pane dispatch capacity, free-pane eligibility, max_inflight semantics, the N/M example, and explicit non-goals in README and the rendered tasks guide. Verified aiswarm instructions tasks renders the guidance; make test-swarm passed (47 tests).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Documented the dispatcher one-task-per-free-pane policy in README and aiswarm instructions tasks, including eligibility, max_inflight, N/M example, and non-goals. Verified rendered guide and make test-swarm (47 passed).
<!-- SECTION:FINAL_SUMMARY:END -->
