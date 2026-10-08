---
id: TASK-62
title: Add supported session-worker restart without stopping tmux panes
status: Done
assignee:
  - '@codex'
created_date: '2026-08-03 15:27'
updated_date: '2026-08-03 15:32'
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
modified_files:
  - swarm/babysitctl.py
  - swarm/cli.py
  - swarm/instructions.py
  - README.md
  - test_swarm.py
priority: high
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
aiswarm tasks and babysit are loop groups inside one long-lived session worker that also delivers durable comms. Toggling aiswarm tasks stop/start changes the group enable flag but intentionally leaves the session worker process alive. During nudge development this means edited Python dispatcher code is not re-imported: aiswarm tasks once -D uses fresh code and can show a valid claim while the live worker continues running stale code and does nothing. Operators currently have no supported way to reload only the shared worker; aiswarm stop is too broad because it tears down the tmux session and agent panes, while manually validating and killing session_worker.pid is an unsafe implementation detail. Provide an explicit worker-only restart/reload lifecycle that preserves the tmux session, agent processes, monitors, durable comms database/cursors, task assignment state, and enabled group configuration. Clarify in help/docs that tasks stop/start toggles a group and is not a code reload.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A supported CLI command restarts or reloads the swarm swarm session worker without stopping or recreating tmux panes or agent processes
- [x] #2 After restart, the worker imports current installed or editable-source Python code and resumes enabled tasks, babysit, and comms groups according to existing configuration
- [x] #3 Task assignment state, durable event log, delivery cursors, and pending events survive the worker restart without duplicate claims or message loss
- [x] #4 The command validates the PID belongs to the expected swarm session worker and fails safely for missing, stale, malformed, or unexpected PID state
- [x] #5 Help and workflow documentation explicitly state that tasks stop/start only toggles the tasks group and does not restart the shared worker
- [x] #6 Tests cover worker-only restart, preserved tmux session identity, state recovery, pending comms delivery, and stale PID handling
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a worker restart lifecycle that validates the recorded PID command belongs to this session/config, terminates only that process, waits for exit, and launches a fresh interpreter.
2. Expose it as aiswarm worker restart with dry-run support; do not mutate tmux, task state, group enable flags, pane specs, or comms storage.
3. Add lifecycle/CLI tests covering preserved runtime files and tmux identity, pending comms state, fresh launch, and malformed/stale/unexpected PID failures.
4. Clarify tasks stop/start semantics in CLI help, workflow guidance, and README; run the full suite and finalize.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented aiswarm worker restart. It verifies /proc/<pid>/cmdline exactly matches the expected session_worker.py and resolved config, sends SIGTERM only to that process, waits up to 10 seconds, and launches a fresh interpreter from the current installation/source tree. It intentionally preserves runtime group/spec/task files and comms.db. Tests verify no tmux stop path, replacement PID propagation, task/group/spec preservation, real SQLite cursor and pending-event preservation, and safe missing/malformed/stale/unexpected PID failures. Validation: make test passed (30 monitor + 101 swarm tests); focused restart tests passed after final strict argv validation.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added a supported worker-only code reload via aiswarm worker restart, preserving tmux panes, agents, monitors, enabled groups, task assignments, and durable comms state. Added strict PID ownership validation, bounded graceful shutdown, fresh interpreter launch, CLI/help/README guidance, and lifecycle regressions. Full suite passes.
<!-- SECTION:FINAL_SUMMARY:END -->
