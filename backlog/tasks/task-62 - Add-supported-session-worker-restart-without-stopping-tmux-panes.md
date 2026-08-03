---
id: TASK-62
title: Add supported session-worker restart without stopping tmux panes
status: To Do
assignee: []
created_date: '2026-08-03 15:27'
labels:
  - worker
  - lifecycle
  - developer-experience
  - tasks
dependencies: []
references:
  - swarm/babysitctl.py
  - swarm/tasksctl.py
  - swarm/cli.py
  - session_worker.py
  - test_swarm.py
documentation:
  - README.md
priority: high
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
aiswarm tasks and babysit are loop groups inside one long-lived session worker that also delivers durable comms. Toggling aiswarm tasks stop/start changes the group enable flag but intentionally leaves the session worker process alive. During nudge development this means edited Python dispatcher code is not re-imported: aiswarm tasks once -D uses fresh code and can show a valid claim while the live worker continues running stale code and does nothing. Operators currently have no supported way to reload only the shared worker; aiswarm stop is too broad because it tears down the tmux session and agent panes, while manually validating and killing session_worker.pid is an unsafe implementation detail. Provide an explicit worker-only restart/reload lifecycle that preserves the tmux session, agent processes, monitors, durable comms database/cursors, task assignment state, and enabled group configuration. Clarify in help/docs that tasks stop/start toggles a group and is not a code reload.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A supported CLI command restarts or reloads the swarm swarm session worker without stopping or recreating tmux panes or agent processes
- [ ] #2 After restart, the worker imports current installed or editable-source Python code and resumes enabled tasks, babysit, and comms groups according to existing configuration
- [ ] #3 Task assignment state, durable event log, delivery cursors, and pending events survive the worker restart without duplicate claims or message loss
- [ ] #4 The command validates the PID belongs to the expected swarm session worker and fails safely for missing, stale, malformed, or unexpected PID state
- [ ] #5 Help and workflow documentation explicitly state that tasks stop/start only toggles the tasks group and does not restart the shared worker
- [ ] #6 Tests cover worker-only restart, preserved tmux session identity, state recovery, pending comms delivery, and stale PID handling
<!-- AC:END -->
