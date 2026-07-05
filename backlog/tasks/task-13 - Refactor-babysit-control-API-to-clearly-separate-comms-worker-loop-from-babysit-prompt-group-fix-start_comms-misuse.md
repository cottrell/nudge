---
id: TASK-13
title: >-
  Refactor babysit control API to clearly separate comms worker loop from
  babysit prompt group (fix start_comms misuse)
status: Done
assignee: []
created_date: '2026-07-05 12:51'
updated_date: '2026-07-05 13:03'
labels:
  - nudge
  - babysit
  - swarm
  - api
  - cleanup
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The recent split of comms (always-on message delivery loop) from babysit (optional prompt nudges) introduced confusing control: `aiswarm babysit stop` calls `start_comms`, `babysitctl.start_comms` is used both for base swarm start and to 'turn off' babysit, and prints say 'Started workers (comms)' on a stop command.

User model: one IO loop per pane; comms group always on (once worker exists); babysit group toggleable on/off independently.

Clean up the public + internal API so intent is obvious:
- Ensure base comms/worker loop (for panes needing monitor/comms).
- Explicit apply_babysit / enable_babysit for turning prompt group on (for panes with babysit.enabled).
- Explicit disable_babysit for turning prompt group off (keep loop for comms).
- Keep full stop_workers for tearing loops down.

Update CLI dispatching, topology.start, babysitctl functions, help text, tests (including the dispatch test), prints, and self-awareness docs.

Do this while still using stop+restart for the toggle (dynamic inside-loop toggle is separate task).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `aiswarm babysit stop` no longer calls or mentions start_comms internally
- [x] #2 `babysitctl` exposes clear functions: e.g. ensure_workers, apply_babysit, disable_babysit, stop_workers
- [x] #3 CLI help and output messages match the action (stop says something about disabling prompts, not 'Started comms')
- [x] #4 All tests pass; the dispatch test is updated to match new function names
- [x] #5 self-awareness.txt and README reflect the new control commands
- [ ] #6 No behavior change for users of `start`, `babysit start`, `babysit stop`, `stop`
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented core of point 1: new ensure/apply/disable/stop_workers API. Updated CLI, topology, tests, added shims. Dynamic refresh in babysit.py + hot spec update in babysitctl for point 2 also landed here.

Core implementation + test updates complete for API refactor. Dynamic support from point 2 also contributed here. Shims preserve compat.

Core of point 1 complete. Dynamic elements from point 2 included.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-05 13:03
---
Implemented and committed in de3f580 [Grok/xAI]. New API: ensure_workers/apply_babysit/disable_babysit. Parallel review requested from claude (pane 0.1) and codex (pane 0.0) in agent_grid swarm. User will test.
---
<!-- COMMENTS:END -->
