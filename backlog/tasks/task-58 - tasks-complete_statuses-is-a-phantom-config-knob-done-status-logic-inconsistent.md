---
id: TASK-58
title: >-
  tasks: complete_statuses is a phantom config knob; done-status logic
  inconsistent
status: To Do
assignee: []
created_date: '2026-07-29 15:49'
labels: []
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_complete_statuses reads getattr(cfg.tasks, "complete_statuses", None) but TasksSpec has no such field and _fill_tasks never parses it from YAML — setting tasks.complete_statuses in a swarm config is silently ignored and the dependency gate always uses {"done"}. Meanwhile view_assignment separately hardcodes status == "done" for clearing assignments. Either wire complete_statuses through TasksSpec/_fill_tasks/effective_config_dict/desired_spec properly, or delete the indirection and hardcode consistently in one place. Whichever way, dependency completion and assignment completion must use the same predicate (view_completed_task archival handling included).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 setting tasks.complete_statuses in YAML either works end-to-end or is rejected/absent (no silent ignore)
- [ ] #2 dependency gate and view_assignment share one is-complete predicate
- [ ] #3 test covers a non-default complete status if the knob is kept
<!-- AC:END -->
