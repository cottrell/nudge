---
id: TASK-38
title: 'tasks: claim failure must not leave inconsistent pane state'
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 20:49'
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
- [x] #1 failed claim does not write local assignment
- [x] #2 failed deliver after claim is logged and optionally retried as chase
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Make each new-claim attempt catch and report claim failures without altering persisted assignment state.
2. Persist the successful backlog claim before attempting delivery, retaining it for the existing chase flow if delivery fails, and log the delivery error.
3. Add focused dispatcher tests for both failure paths and run the swarm test suite.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.0 (session nudge).

Implemented guarded claim/delivery sequencing: claim failures are logged without state writes; successful claims are persisted before delivery so delivery failures are logged and retried by the existing chase path.

Validation passed: make test-swarm (58 passed), including the two failure-path regression tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Guarded dispatcher claim and delivery errors: failed claims leave no assignment, and failed delivery retains the claim for chase retry with a warning. Verified by two focused tests and make test-swarm (58 passed).
<!-- SECTION:FINAL_SUMMARY:END -->
