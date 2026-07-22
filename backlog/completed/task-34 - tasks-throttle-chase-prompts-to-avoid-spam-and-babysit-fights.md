---
id: TASK-34
title: 'tasks: throttle chase prompts to avoid spam and babysit fights'
status: Done
assignee:
  - 'aiswarm:nudge:0.5'
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 14:01'
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
- [x] #1 configurable min seconds between chases per assignment
- [x] #2 docs note interaction with babysit
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.5 (session nudge).

Starting: add min_chase_secs throttle + shorter chase prompt + docs (babysit interaction).

Implemented min_chase_secs (default 300) on TasksSpec; chase_assigned skips when last_chased_at/claimed_at within window; short chase prompt (no full snapshot); last_chased_at persisted; README + instructions note babysit vs tasks fight; tests: chase_due, throttle skip/fire, config override. All 56 test_swarm passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Throttle tasks chase prompts: configurable min_chase_secs (default 300s) per assignment using last_chased_at/claimed_at; shorter chase reminder without snapshot; docs cover babysit interaction.
<!-- SECTION:FINAL_SUMMARY:END -->
