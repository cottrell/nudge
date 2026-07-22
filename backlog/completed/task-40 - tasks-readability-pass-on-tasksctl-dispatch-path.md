---
id: TASK-40
title: 'tasks: readability pass on tasksctl dispatch path'
status: Done
assignee: []
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 13:56'
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
- [x] #1 is_pane_free reuses pane_ready_for_prompt
- [x] #2 shared helper for Done/missing/unassigned
- [x] #3 dispatch_once reads as ordered steps without deep nesting
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Readability: is_pane_free→pane_ready_for_prompt; view_assignment shared; dispatch_once steps clear.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Dispatch path structured; shared assignment lifecycle helper.
<!-- SECTION:FINAL_SUMMARY:END -->
