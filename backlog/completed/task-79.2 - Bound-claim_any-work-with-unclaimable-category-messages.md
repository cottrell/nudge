---
id: TASK-79.2
title: Bound claim_any work with unclaimable category messages
status: Done
assignee:
  - '@claude'
created_date: '2026-10-01 09:06'
updated_date: '2026-10-01 09:11'
labels:
  - routing
  - comms
dependencies: []
parent_task_id: TASK-79
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
claim_any now fetches every unclaimed __any__ event and parses metadata in Python while holding BEGIN IMMEDIATE. A category with no eligible pane stays pending by design, so each idle pane repeats a full scan on every poll; long queues also delay or block sends and existing plain any deliveries.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Idle-pane claim cost stays bounded or scales with eligible messages rather than the full orphaned category queue
- [ ] #2 A plain any message behind unclaimable category messages remains deliverable
- [ ] #3 Regression coverage exercises a sizeable unclaimable category queue and concurrent/plain-any delivery
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed in follow-up commit; verified by new tests, make test passes (137+30).
<!-- SECTION:FINAL_SUMMARY:END -->
