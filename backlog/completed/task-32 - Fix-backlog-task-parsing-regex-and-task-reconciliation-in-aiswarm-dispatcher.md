---
id: TASK-32
title: Fix backlog task parsing regex and task reconciliation in aiswarm dispatcher
status: Done
assignee:
  - 'aiswarm:cd:0.4'
created_date: '2026-07-22 11:15'
labels: []
dependencies: []
modified_files:
  - swarm/tasksctl.py
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The aiswarm tasks dispatcher fails to process tasks containing bracketed labels (e.g. [enhancement]) and subtask decimals (e.g. TASK-93.1) correctly. Additionally, when a task is completed/archived, backlog task <id> --plain returns Task not found on stderr, causing the dispatcher's reconcile loop to stall indefinitely on completed pane assignments.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 TASK_LINE_RE successfully parses task lines containing bracketed types and decimal IDs
- [ ] #2 Reconciliation loop successfully handles not found on stderr, freeing assigned panes on completed tasks
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Modified TASK_LINE_RE regex to support bracketed labels and decimals, and updated reconcile_assignments to combine stdout and stderr and check for not found to successfully release pane assignments.
<!-- SECTION:FINAL_SUMMARY:END -->
