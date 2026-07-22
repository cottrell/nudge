---
id: TASK-38
title: 'tasks: claim failure must not leave inconsistent pane state'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: claim_task can fail after we intended to assign; or log_send fails after claim. Pane/local state and backlog can disagree.

Fix: order operations with clear rollback or only write local assignment after successful claim+deliver; surface errors in dispatcher log.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 failed claim does not write local assignment
- [ ] #2 failed deliver after claim is logged and optionally retried as chase
<!-- AC:END -->
