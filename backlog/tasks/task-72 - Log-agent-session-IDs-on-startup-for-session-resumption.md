---
id: TASK-72
title: Log agent session IDs on startup for session resumption
status: Done
assignee:
  - '@grok'
created_date: '2026-09-13 11:17'
updated_date: '2026-09-13 12:59'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agent processes started inside swarm panes often lose their conversation context upon crashes or restarts unless their underlying session ID is recorded. Other agent harness projects capture or pre-assign session IDs at launch to enable easy session resumption.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Investigate session ID creation and capture mechanisms across supported agent CLIs (Claude, Codex, Antigravity, Grok).
- [x] #2 Record or pre-assign agent session IDs on startup and log them to standard metadata/runtime storage.
- [x] #3 Provide an easy way/command to retrieve active or past session IDs for resuming crashed agent sessions.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add swarm/session_ids.py: mint Claude/Grok --session-id at launch; discover via argv, ~/.claude/sessions/<pid>.json, ~/.grok/active_sessions.json, /proc/pid/fd. No newest-file. 2. On aiswarm start, mint into launched command, persist records in runtime_dir/session-ids.json + .aiswarm/session-ids.json, merge into runtime.json. 3. aiswarm sessions lists pane/agent/id/resume command and refreshes live pids. 4. Unit tests for mint, pid bind, no cwd-newest collision, CLI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Mint Claude/Grok --session-id at launch; discover others via pane PID (argv, ~/.claude/sessions/<pid>.json, ~/.grok/active_sessions.json, /proc fd). No newest-file-in-cwd. Persist runtime_dir/session-ids.json + next to config. CLI: aiswarm sessions. Validation: uv run pytest test_swarm.py -q → 120 passed (mint, pid-bind vs newer cwd file, agy/codex fd, runtime map, CLI --no-refresh).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
aiswarm start mints Claude/Grok session IDs and records them; live panes are bound by PID (not newest-cwd). aiswarm sessions prints id + resume command. Verified with test_swarm.py (120 passed), including a same-cwd two-pane grok case where newest-file would have been wrong.
<!-- SECTION:FINAL_SUMMARY:END -->
