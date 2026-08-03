---
id: TASK-61
title: Make tasks dispatcher match ready tasks to eligible panes task-first
status: To Do
assignee: []
created_date: '2026-08-03 15:11'
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
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tasks dispatcher can leave valid work idle when ready To Do tasks are preassigned to specific swarm panes. In demo-data, free panes were ordered 0.2, 0.4, 0.5 and the sole ready task was preassigned to aiswarm:cd:0.4. The claim loop examined pane 0.2 first, found neither a task assigned to 0.2 nor an unassigned task, then exited the whole pane loop. It never considered free pane 0.4, so both tasks status and tasks once -D reported no dispatch despite a ready task and its eligible free pane. Scheduling should be task-centric or otherwise perform complete matching: prioritize ready preassigned tasks and match each to its designated eligible pane, then distribute unassigned ready tasks among remaining free panes. One unmatched pane must not prevent later pane/task matches.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A ready To Do task preassigned to a later free pane is dispatched to that pane even when earlier free panes have no matching work
- [ ] #2 Multiple ready preassigned tasks are matched to their respective eligible free panes before unassigned tasks are distributed
- [ ] #3 An unmatched free pane does not terminate or starve matching for remaining panes and tasks
- [ ] #4 Dependency, label, idle, max-inflight, skip-assignee, and one-task-per-pane gates continue to apply
- [ ] #5 Dry-run and live dispatch report the same planned task-to-pane matches
- [ ] #6 Regression tests cover the 0.2-first and task-for-0.4 reproduction plus mixed preassigned and unassigned candidates
<!-- AC:END -->
