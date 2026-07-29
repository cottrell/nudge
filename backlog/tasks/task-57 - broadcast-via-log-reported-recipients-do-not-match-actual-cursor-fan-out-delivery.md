---
id: TASK-57
title: >-
  broadcast --via-log: reported recipients do not match actual cursor fan-out
  delivery
status: Done
assignee:
  - '@aiswarm:nudge:0.4'
created_date: '2026-07-29 15:49'
updated_date: '2026-07-29 16:12'
labels: []
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
topology.broadcast with via_log prints "log-broadcast to <target>" for agent panes (filtered by pane.agent and monitor unless -A), but log_broadcast writes ONE __broadcast__ event and actual delivery is per-pane broadcast-cursor fan-out in pane_worker._drain_comms, which runs for every pane the session worker services (all comms-enabled panes, including shell/log panes with comms on). So: (a) the printed recipient list can both under- and over-state real delivery; (b) --include-nonmonitored has no effect on the log path. Decide the intended semantics: either make _drain_comms filter broadcasts by pane agent/monitor flags recorded in the spec, or make the CLI print the true fan-out set. Also log_send/log_broadcast do not validate the recipient pane exists in the config — a typo like `aiswarm send 0.9 msg` queues an event nobody will ever drain, silently.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 printed broadcast recipients equal the panes that will actually receive the event via cursor fan-out
- [x] #2 documented (or implemented) behaviour for --include-nonmonitored under --via-log
- [x] #3 aiswarm send to a pane not present in the config warns (event may still be logged)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add 'monitor' field to pane spec written in desired_spec in swarm/babysitctl.py and pane_worker.py.
2. In log_broadcast, accept include_nonmonitored parameter and store it in meta JSON in the SQLite comms db.
3. In swarm/topology.py, pass include_nonmonitored to log_broadcast when calling it.
4. Modify _drain_comms in pane_worker.py to read the spec (loading from /tmp/nudge-swarm/<session>/babysit-W-N.json if not passed) and filter broadcast messages.
5. In swarm/cli.py, warning if the recipient pane is not present in the config during the 'send' command.
6. Write tests to verify the behavior of broadcast and warnings.
7. Run all tests and complete the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.4 (session nudge).

Validation passed: uv run pytest test_swarm.py -v passed all tests including the new test_broadcast_via_log_filtering_and_warning.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: aiswarm:nudge:0.1
created: 2026-07-29 16:12
---
## Peer review (aiswarm:nudge:0.1 / codex light)\nVerdict: APPROVE\nACs: #1 holds, #2 holds, #3 holds. The CLI now computes the log-broadcast recipient set from the same pane filters it uses for direct broadcast, log_broadcast carries include_nonmonitored in event meta, _drain_comms honors monitor/include-nonmonitored when fanning out broadcasts, and cli send warns on config-missing recipients.\nFindings: None blocking. I spot-checked [swarm/topology.py](~/dev/nudge/swarm/topology.py), [swarm/common.py](~/dev/nudge/swarm/common.py), [swarm/cli.py](~/dev/nudge/swarm/cli.py), and [test_swarm.py](~/dev/nudge/test_swarm.py::test_broadcast_via_log_filtering_and_warning); the test exercises both monitored-only and include-nonmonitored log delivery plus the send warning.\nResidual risks: Delivery still depends on the per-pane spec JSON being present and current in /tmp/nudge-swarm/<session>/babysit-*.json; if a stale spec were left behind, broadcast fan-out could lag the live config until the worker refreshes it. I did not find evidence that this breaks the ACs or the existing test path.
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented log_broadcast filtering in _drain_comms based on agent and monitor spec flags, propagated --include-nonmonitored via event meta, and printed warnings when sending to non-existent panes. Verified with test_broadcast_via_log_filtering_and_warning.
<!-- SECTION:FINAL_SUMMARY:END -->
