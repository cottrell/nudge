---
id: TASK-33
title: 'tasks: do not treat monitor unknown as idle for claim/chase'
status: Done
assignee:
  - 'aiswarm:nudge:0.1'
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 14:00'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: pane_ready_for_prompt / is_pane_free treat monitor state unknown like idle. If socket missing or probe fails, dispatcher may claim or chase when the pane is not actually free.

Fix: only treat idle as ready for new claim and chase (or require explicit policy). Log unknown separately. Tests for unknown → no claim/chase when require_idle.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 unknown is not treated as idle when require_idle true
- [x] #2 unit/integration coverage for missing socket
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Tighten pane readiness so require_idle accepts only explicit idle, not unknown.\n2. Add regression coverage for missing monitor socket on claim/chase paths.\n3. Run targeted tests and record the results in the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.1 (session nudge).

Tightened pane_ready_for_prompt/is_pane_free so require_idle only accepts explicit idle; unknown and missing monitor sockets now block claim/chase. Added regression coverage for unknown monitor state plus missing-socket claim/chase paths. Verified with pytest -q test_swarm.py (53 passed).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Restricted tasks claim/chase readiness to explicit idle only; unknown and missing monitor sockets now block dispatch. Verified with pytest -q test_swarm.py (53 passed), including unknown-state and missing-socket regressions for both claim and chase paths.
<!-- SECTION:FINAL_SUMMARY:END -->
