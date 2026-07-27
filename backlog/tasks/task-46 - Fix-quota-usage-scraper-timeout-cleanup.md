---
id: TASK-46
title: Fix quota usage scraper timeout cleanup
status: Done
assignee:
  - '@codex'
created_date: '2026-07-27 10:45'
updated_date: '2026-07-27 10:47'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quota usage scripts create temporary codex/claude/agy tmux sessions named <agent>-usage-<pid>. get_cached_provider_usage uses subprocess.run(timeout=30); a timeout kills the wrapper before its EXIT trap runs, leaving live agent sessions. Ensure timeout handling explicitly removes the exact temporary tmux session, and remove confirmed leaked usage sessions.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Timed-out quota scraper removes its exact temporary tmux session
- [x] #2 Existing leaked codex/claude/agy usage sessions are removed only after exact-name confirmation
- [x] #3 Relevant tests pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Replace direct timeout execution with a process whose exact temporary session name can be removed on timeout.
2. Add a focused regression test for timeout cleanup.
3. Verify tests, then remove only confirmed agent-usage sessions and record the result.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added explicit timeout cleanup keyed to the wrapper PID-derived exact tmux session name. Removed seven confirmed leaked usage sessions: five codex and two claude. The focused timeout cleanup regression passed. make test-swarm currently has three unrelated failures caused by the separate uncommitted fail-closed task-detail change in swarm/tasksctl.py.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed quota scraper timeout cleanup by removing the exact temporary usage session before killing the wrapper, and removed confirmed leaked sessions. Verified with focused regression test.
<!-- SECTION:FINAL_SUMMARY:END -->
