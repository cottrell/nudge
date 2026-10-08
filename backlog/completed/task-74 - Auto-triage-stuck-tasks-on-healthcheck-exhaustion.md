---
id: TASK-74
title: Auto-triage stuck tasks on healthcheck exhaustion
status: Done
assignee:
  - antigravity
created_date: '2026-09-15 13:08'
updated_date: '2026-09-15 13:09'
labels: []
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When a task worker exhausts its healthcheck budget on a task, spawn a triage backlog task for another free pane to inspect the pane scrollback and resolve or unassign the stuck task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 tasksctl creates a triage task when healthcheck budget is exhausted
- [ ] #2 triage task is created with require_label if configured
- [ ] #3 avoids creating duplicate triage tasks for the same exhaustion
- [ ] #4 tests pass in test_swarm.py
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented automatic triage task creation on healthcheck exhaustion. Added test in test_swarm.py.
<!-- SECTION:FINAL_SUMMARY:END -->
