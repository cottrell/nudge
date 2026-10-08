---
id: TASK-66
title: Add single-consumer `aiswarm send any` routing
status: Done
assignee:
  - '@codex'
created_date: '2026-08-24 13:15'
updated_date: '2026-08-24 13:19'
labels: []
dependencies: []
modified_files:
  - README.md
  - pane_worker.py
  - swarm/cli.py
  - swarm/common.py
  - swarm/instructions.py
  - swarm/topology.py
  - test_swarm.py
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Allow producers such as a voice MCP to submit a durable note to a swarm without selecting a pane. The always-running comms worker must route each note to exactly one eligible idle pane, independently of the optional Backlog tasks dispatcher.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `aiswarm send any MESSAGE` durably queues the message when no pane is immediately available
- [x] #2 Exactly one eligible pane receives each queued any-target message
- [x] #3 Routing operates while the Backlog tasks dispatcher is stopped
- [x] #4 Panes with active Backlog assignments are not selected
- [x] #5 The comms log records queueing, pane selection, and delivery for audit
- [x] #6 Tests cover idle selection, busy waiting, atomic single delivery, and task-assignment exclusion
- [x] #7 README and CLI/instructions document the any target and its semantics
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extend the SQLite comms log with an atomic single-consumer claim record for `any` events.
2. Let idle pane workers claim one queued event only when they have no active Backlog assignment, then deliver through the normal pane stream.
3. Update CLI warnings, log display semantics, help/instructions, and README.
4. Add focused queue/worker tests, run the full test suite, finalize the Backlog task, and commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added WAL-backed `__any__` queue events and an atomic `any_claims` selection record. Idle comms workers route a claim into the existing per-pane delivery/ack stream, while panes present in local task assignment state are excluded. Updated CLI help, pending-log summary, agent instructions, README, and focused tests.

Validation: `make test` passed all 30 monitor tests and all 105 swarm tests. Focused tests verify busy-to-idle waiting without the tasks enable flag, one winner under two concurrent claims, task-assignment exclusion, CLI `any` queueing, and queue/selection/ack audit events.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented durable `aiswarm send any`: the always-on comms worker atomically selects exactly one idle pane, excludes locally task-assigned panes, and delivers through the existing acknowledged pane log. Documented the CLI and verified with `make test` (30 monitor + 105 swarm tests).
<!-- SECTION:FINAL_SUMMARY:END -->
