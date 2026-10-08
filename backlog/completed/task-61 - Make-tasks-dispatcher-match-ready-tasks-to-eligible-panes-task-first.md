---
id: TASK-61
title: Make tasks dispatcher match ready tasks to eligible panes task-first
status: Done
assignee:
  - '@codex'
created_date: '2026-08-03 15:11'
updated_date: '2026-08-03 15:14'
labels:
  - tasks
  - dispatcher
  - scheduling
dependencies: []
references:
  - swarm/tasksctl.py
  - test_swarm.py
documentation:
  - README.md
modified_files:
  - swarm/tasksctl.py
  - test_swarm.py
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tasks dispatcher can leave valid work idle when ready To Do tasks are preassigned to specific swarm panes. In demo-data, free panes were ordered 0.2, 0.4, 0.5 and the sole ready task was preassigned to aiswarm:cd:0.4. The claim loop examined pane 0.2 first, found neither a task assigned to 0.2 nor an unassigned task, then exited the whole pane loop. It never considered free pane 0.4, so both tasks status and tasks once -D reported no dispatch despite a ready task and its eligible free pane. Scheduling should be task-centric or otherwise perform complete matching: prioritize ready preassigned tasks and match each to its designated eligible pane, then distribute unassigned ready tasks among remaining free panes. One unmatched pane must not prevent later pane/task matches.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A ready To Do task preassigned to a later free pane is dispatched to that pane even when earlier free panes have no matching work
- [x] #2 Multiple ready preassigned tasks are matched to their respective eligible free panes before unassigned tasks are distributed
- [x] #3 An unmatched free pane does not terminate or starve matching for remaining panes and tasks
- [x] #4 Dependency, label, idle, max-inflight, skip-assignee, and one-task-per-pane gates continue to apply
- [x] #5 Dry-run and live dispatch report the same planned task-to-pane matches
- [x] #6 Regression tests cover the 0.2-first and task-for-0.4 reproduction plus mixed preassigned and unassigned candidates
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add regression coverage for a later free pane with a preassigned To Do task and for mixed preassigned/unassigned candidates under constrained capacity.
2. Prioritize free panes that have preassigned candidates, then distribute unassigned candidates; continue past unmatched panes.
3. Run focused and full tests, document evidence, finalize, and commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed reachable pane-order bug: the no-match branch exited the full free-pane loop. Implemented preassigned-pane-first stable ordering, continued past unmatched panes, and counted dry-run plans against max_inflight. Validation: make test passed (30 monitor tests, 95 swarm tests), including exact 0.2-before-0.4 reproduction and mixed preassigned/unassigned dry-run/live parity.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed task matching so ready preassigned tasks are offered to their eligible free panes before unassigned work, and unmatched panes no longer halt later matches. Dry-run now observes max_inflight identically to live dispatch. Added regression coverage for the reported 0.2/0.4 case and mixed scheduling; make test passes.
<!-- SECTION:FINAL_SUMMARY:END -->
