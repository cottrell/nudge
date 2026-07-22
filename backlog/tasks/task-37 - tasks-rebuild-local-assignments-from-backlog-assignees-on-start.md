---
id: TASK-37
title: 'tasks: rebuild local assignments from backlog assignees on start'
status: Done
assignee:
  - 'aiswarm:nudge:0.3'
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 14:00'
labels: []
dependencies: []
priority: high
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: local state.json is sole memory of pane↔task. Dispatcher restart or deleted state forgets claims; backlog still has aiswarm:session:pane assignees but chase/claim logic will not pick them up as open work (unassigned_only).

Fix: on start or each pass, scan In Progress (or ingest+assigned) for assignee matching claim prefix and rehydrate assignments.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 restart with empty state.json recovers aiswarm:session:pane claims from backlog
- [x] #2 does not double-claim free To Do already owned by a pane
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.3 (session nudge).

## Implementation Summary

Added **recover_assignments_from_backlog()** function (swarm/tasksctl.py L540-599) to rebuild pane↔task assignments from backlog on dispatcher startup.

**How it works:**
1. Scans backlog for all ingest statuses (To Do, In Progress, etc.)
2. For each pane, searches for tasks assigned to `aiswarm:session:pane` pattern
3. Rebuilds local state.json with recovered assignments
4. Does NOT override existing local assignments (local takes precedence)
5. Marks recovered assignments with `recovered_at` timestamp

**Integration:**
- Called at start of `dispatch_once()` (L672) before reconcile/chase/claim
- Persists recovered state to disk via `save_state()`

**Testing:**
- Added test_recover_assignments_from_backlog_empty_state_finds_existing_claims ✓
- Added test_recover_assignments_does_not_override_existing_local_assignments ✓
- All 52 tests pass

**Risk mitigation:**
- Empty state.json on restart no longer loses assignments
- Backlog becomes source of truth for recovery
- Dispatcher seamlessly continues work across restarts
<!-- SECTION:NOTES:END -->
