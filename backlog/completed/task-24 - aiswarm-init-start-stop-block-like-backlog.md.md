---
id: TASK-24
title: aiswarm init start stop block like backlog.md
status: Done
assignee: []
created_date: '2026-07-15 10:36'
updated_date: '2026-07-16 09:11'
labels: []
dependencies: []
modified_files:
  - swarm/init.py
  - swarm/topology.py
  - test_swarm.py
  - AGENTS.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
For example: <!-- AISWARM/NUDGE GUILDELINES START -->
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 AGENTS.md swarm section wrapped in AISWARM/NUDGE GUIDELINES START/END markers
- [x] #2 init upserts marked block without duplicating
- [x] #3 start refreshes marked block from session name
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wrap AGENTS.md swarm guidance in <!-- AISWARM/NUDGE GUIDELINES START/END --> markers (like backlog.md). Upsert on init+start; remove on stop. Update tests and repo AGENTS.md.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Managed AGENTS.md swarm guidance with backlog-style markers:
<!-- AISWARM/NUDGE GUIDELINES START --> ... END -->

- init upserts the marked block (replaces legacy ## Swarm)
- start refreshes the block for the session
- remove_agents_block helper available; stop leaves docs in place so git stays clean
- Tests cover create/upsert/remove; all 43 swarm tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
