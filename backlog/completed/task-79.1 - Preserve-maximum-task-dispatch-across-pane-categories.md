---
id: TASK-79.1
title: Preserve maximum task dispatch across pane categories
status: Done
assignee:
  - '@claude'
created_date: '2026-10-01 09:06'
updated_date: '2026-10-01 09:11'
labels:
  - routing
  - dispatcher
dependencies: []
parent_task_id: TASK-79
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With a heavy-only pane and a light-only pane free, a general task ordered before a heavy task is assigned to the heavy pane. The heavy task then remains unclaimed although two free panes and two ready tasks existed. The new cat: eligibility gate makes the pane-first greedy order in _claim_new_onto_free leave compatible work idle.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 General and category-constrained ready tasks are paired so both can dispatch when compatible free panes exist
- [ ] #2 Preassigned tasks, priority, dependencies, max_inflight, and dry-run/live parity remain correct
- [ ] #3 Regression coverage includes one heavy pane, one light pane, a general task ordered before a heavy task
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed in follow-up commit; verified by new tests, make test passes (137+30).
<!-- SECTION:FINAL_SUMMARY:END -->
