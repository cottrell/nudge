---
id: TASK-31
title: 'Document aiswarm tasks dispatch: one-per-free-pane, not dump-all'
status: To Do
assignee: []
created_date: '2026-07-22 08:48'
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
- [ ] #1 README tasks section states: one task per free pane per pass; remaining To Dos wait for next free slot / poll
- [ ] #2 aiswarm instructions tasks states the same policy + free-pane definition + max_inflight
- [ ] #3 Explicit non-goals: no dump-all, no multi-task queue per pane while assigned
- [ ] #4 Example: N free panes, M candidates → min(N,M) claims this pass (respect max_inflight)
<!-- AC:END -->
