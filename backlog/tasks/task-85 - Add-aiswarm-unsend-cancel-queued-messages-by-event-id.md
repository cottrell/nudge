---
id: TASK-85
title: 'Add aiswarm unsend: cancel queued messages by event id'
status: In Progress
assignee: []
created_date: '2026-10-03 11:37'
updated_date: '2026-10-03 11:38'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agents can cancel a sent message by id (printed by send) before the comms consumer delivers it. Tombstone via cursor_acks; consumer claims atomically before tmux-send so unsend races are safe; unsend appends an ack event to the log. Covers pane, __any__, __broadcast__ queues.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 unsend <id> cancels undelivered pane/any/scheduled messages
- [ ] #2 consumer claim before tmux-send; unsend after delivery reports too late
- [ ] #3 unsend appends ack event (delivery=unsent) to log
- [ ] #4 tests in test_swarm.py
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. common.py: claim_delivery (atomic), unsend_event, exclude cancelled in any/broadcast queries. 2. pane_worker: claim before tmux-send. 3. cli: unsend subcommand. 4. tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: common.claim_delivery/unsend_event, pane_worker claims before send, cli unsend, 5 tests. Uncommitted (test_swarm.py/topology.py had pre-existing changes).
<!-- SECTION:NOTES:END -->
