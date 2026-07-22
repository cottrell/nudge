---
id: TASK-34
title: 'tasks: throttle chase prompts to avoid spam and babysit fights'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: chase_assigned re-sends full task snapshot every poll (~60s) while pane idle. Spams agent context and fights babysit on same pane.

Design: min chase interval, shorter chase prompt, or skip if last chase recent. Prefer not both babysit+tasks on same pane (already warned).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 configurable min seconds between chases per assignment
- [ ] #2 docs note interaction with babysit
<!-- AC:END -->
