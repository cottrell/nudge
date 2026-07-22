---
id: TASK-40
title: 'tasks: readability pass on tasksctl dispatch path'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: medium
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tasksctl.py is hard to follow (~650 lines): backlog CLI, free/chase/claim, process control mixed. Duplicate free vs ready helpers; dual import style.

Goals: clear section structure, is_pane_free built on pane_ready_for_prompt, shared assignment health helper, less nesting in dispatch_once. Optional later split file — keep minimal for first pass.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 is_pane_free reuses pane_ready_for_prompt
- [ ] #2 shared helper for Done/missing/unassigned
- [ ] #3 dispatch_once reads as ordered steps without deep nesting
<!-- AC:END -->
