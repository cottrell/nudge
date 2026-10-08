---
id: TASK-50
title: 'tasks: resolve dependencies completed by Backlog archival'
status: Done
assignee:
  - '@codex'
created_date: '2026-07-29 14:50'
updated_date: '2026-07-29 14:52'
labels: []
dependencies: []
modified_files:
  - swarm/tasksctl.py
  - test_swarm.py
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tasks dispatcher treats dependencies moved by backlog task complete into backlog/completed as missing, so ready tasks remain unclaimed while the worker is running. Preserve the actionable-status candidate query, but resolve dependency IDs against completed records as well as editable tasks. Truly missing IDs must remain blocked and visibly diagnosed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A task depending on a completed archived task is claimable
- [x] #2 A genuinely missing dependency remains blocked and is reported as missing
- [x] #3 Status/dry-run output does not present dependency-blocked tasks as dispatchable candidates without explaining the gate
- [x] #4 Regression tests cover archived-completed and genuinely missing dependencies
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a read-only completed-task fallback for dependency lookup when Backlog's editable-task JSON lookup returns not found. 2. Keep genuinely absent IDs blocked and distinguish their diagnostics. 3. Annotate status candidate previews with dependency readiness. 4. Add focused regression tests, run the suite, then finalize and commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented completed-task dependency fallback and readiness-aware status output. Focused regression tests pass; full make test passes (28 monitor tests, 77 swarm tests). Live dry-run against dag-patterns now plans TASK-4 and TASK-6 while correctly blocking TASK-5 on TASK-4.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed dependency resolution for tasks completed into backlog/completed while retaining fail-closed handling for genuinely missing IDs. Status now reports candidate readiness and blocking reasons. Verified by focused regression tests, the full make test suite, and a live dry-run against dag-patterns that selected TASK-4/TASK-6 and blocked TASK-5.
<!-- SECTION:FINAL_SUMMARY:END -->
