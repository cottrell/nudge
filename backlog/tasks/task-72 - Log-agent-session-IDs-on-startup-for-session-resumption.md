---
id: TASK-72
title: Log agent session IDs on startup for session resumption
status: To Do
assignee: []
created_date: '2026-09-13 11:17'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agent processes started inside swarm panes often lose their conversation context upon crashes or restarts unless their underlying session ID is recorded. Other agent harness projects capture or pre-assign session IDs at launch to enable easy session resumption.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Investigate session ID creation and capture mechanisms across supported agent CLIs (Claude, Codex, Antigravity, Grok).
- [ ] #2 Record or pre-assign agent session IDs on startup and log them to standard metadata/runtime storage.
- [ ] #3 Provide an easy way/command to retrieve active or past session IDs for resuming crashed agent sessions.
<!-- AC:END -->
