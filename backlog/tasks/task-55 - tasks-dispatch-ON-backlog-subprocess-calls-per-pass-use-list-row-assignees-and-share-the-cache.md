---
id: TASK-55
title: >-
  tasks dispatch: O(N) backlog subprocess calls per pass; use list-row assignees
  and share the cache
status: To Do
assignee: []
created_date: '2026-07-29 15:48'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Each dispatch pass still spawns ~225ms `backlog` subprocesses proportional to task count, and it runs inline in the session_worker loop, so a slow pass blocks comms delivery and babysit nudges for every pane. Sources (Fable 5 review 2026-07-29): (1) dispatch_once fetches full detail via _task_or_none for EVERY candidate just to read assignees, but `backlog task list --json` rows already include an assignees field (verified against this repo backlog) — recover_assignments_from_backlog and the unassigned_only filter can use list rows and skip detail fetches entirely; detail is only needed for dependency gating of tasks actually about to be claimed and for the claim snapshot. (2) view_assignment (used by reconcile_assignments AND chase_assigned) bypasses the shared per-pass cache, costing 2 extra `backlog task <id> --json` calls per assigned pane per pass. (3) _claim_new_onto_free calls view_task_plain right after _task_or_none cached the same task — refetch; use format_task_snapshot(full). (4) tasksctl.status computes dependency_gate for every candidate (transitive closure, subprocess per uncached dep) for a 15-line display — gate only the displayed 15. Also: validate_tasks_config runs every pass and re-prints the babysit+tasks warning each poll (log spam).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 steady-state pass with K assigned panes and M candidates makes O(ingest_statuses + K) backlog calls, not O(M): no per-candidate detail fetch when list rows carry assignees
- [ ] #2 view_assignment participates in the shared per-pass cache (reconcile + chase reuse one fetch per task)
- [ ] #3 claim snapshot reuses the cached task object instead of a second view fetch
- [ ] #4 tasks status only dependency-gates the tasks it displays
- [ ] #5 test_swarm.py counts backlog invocations per pass and locks the bound
<!-- AC:END -->
