---
id: TASK-41
title: >-
  Please make sure we also include In Progress tasks or whatever it is not just
  To Do in aiswarm tasks
status: Done
assignee:
  - 'aiswarm:nudge:0.2'
created_date: '2026-07-22 13:59'
updated_date: '2026-07-22 20:49'
labels: []
dependencies: []
---

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Default tasks.ingest was ["To Do"] only, which silently broke recover_assignments_from_backlog (TASK-37): after a dispatcher restart it scans cfg.tasks.ingest for assignee-matched tasks, but claimed tasks are always status 'In Progress', so recovery found nothing unless a user manually opted in with ingest: [To Do, In Progress]. Changed the default in swarm/common.py to ["To Do", "In Progress"] so claim/recovery work out of the box; unassigned_only still gates new claims so already-assigned In Progress tasks aren't re-claimed. Updated README.md and swarm/instructions.py docs, renamed the opt-in test to reflect it's now the default, and added test_load_config_tasks_ingest_defaults_to_to_do_and_in_progress. Full suite (28 C + 59 python) passes.
<!-- SECTION:NOTES:END -->
