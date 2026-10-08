---
id: TASK-75
title: Add clear_every and clear_on_claim support for tasks dispatcher
status: Done
assignee:
  - antigravity
created_date: '2026-09-15 13:50'
updated_date: '2026-09-15 13:51'
labels: []
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add per-pane / per-tasks config clear_on_claim (clear context on new task claim) and clear_every (clear context after N task chases/nudges) so tasks dispatcher doesn't blow up agent context windows.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 tasks config supports clear_on_claim and clear_every
- [ ] #2 pane tasks spec overrides work as expected
- [ ] #3 chase/claim sends /clear when due before task prompt
- [ ] #4 all tests pass
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added clear_on_claim (default: true) and clear_every (default: 0) options to TasksSpec. Automatically delivers /clear before claiming new tasks and periodically during task chases.
<!-- SECTION:FINAL_SUMMARY:END -->
