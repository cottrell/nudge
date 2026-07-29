---
id: TASK-56
title: >-
  babysit start --no-action leaks BABYSIT_DRY_RUN into the long-lived session
  worker
status: To Do
assignee: []
created_date: '2026-07-29 15:49'
labels: []
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py sets os.environ["BABYSIT_DRY_RUN"]="1" for --no-action, but the flag only has an effect if THIS invocation happens to spawn the session worker (Popen inherits env). Two failure modes: (a) if the worker is already running, --no-action silently does nothing; (b) if this call spawns the worker, the env var lives for the worker lifetime, so a later plain `babysit start` (or `tasks start`) sees the pid alive, returns early, and all prompt/comms delivery stays disabled with no indication — _deliver/_send_message in pane_worker check the env on every send. The simulate flag must be carried in the per-pane spec json (like via_log) or a runtime flag file the worker re-reads, not process env; and turning it off must not require killing the worker.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 no-action mode is honored regardless of whether the worker was already running
- [ ] #2 plain babysit start after a --no-action start restores real delivery without manually killing session_worker
- [ ] #3 status surfaces when the worker is in no-action/simulate mode
<!-- AC:END -->
