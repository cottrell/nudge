---
id: TASK-15
title: >-
  Clean up naming pollution for comms vs babysit workers (files, functions,
  labels, docs)
status: To Do
assignee: []
created_date: '2026-07-05 12:52'
labels:
  - nudge
  - babysit
  - swarm
  - naming
  - docs
dependencies:
  - TASK-13
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After the comms/babysit split, many names still say 'babysit' even for pure comms workers:
- babysit-*.pid / .log / .json / .state.json for comms-only loops
- babysitctl.py , start/stop functions, labels like 'workers (comms)'
- 'babysit' in runtime paths, self-awareness, help text, etc.

Make names reflect the reality: the worker is the IO loop / comms consumer primarily; babysit is one optional mode/group.

Examples of changes:
- Consider worker-*.pid (or keep for compat, or use pane-worker-)
- Rename babysitctl.py ? or keep but document
- Update _start_workers labels, print messages
- Update docs, runtime map keys if needed (careful with compat), AGENTS, self-awareness
- Function names like start_comms -> ensure_workers

Do after the API refactor so new names are used.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 File names and paths no longer exclusively use 'babysit' for comms workers (or explicit decision + compat note if keeping)
- [ ] #2 Prints, help, and status legends use accurate language ('worker loop', 'comms consumer', 'babysit prompts enabled')
- [ ] #3 Internal functions/labels updated consistently with the 'one loop + two groups' model
- [ ] #4 self-awareness.txt, README, AGENTS.md, backlog docs updated
- [ ] #5 Breaking changes minimized or migration notes added; tests updated
- [ ] #6 No impact on running swarms (or handled)
<!-- AC:END -->
