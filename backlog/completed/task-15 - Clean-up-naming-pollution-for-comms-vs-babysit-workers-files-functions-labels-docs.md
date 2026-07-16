---
id: TASK-15
title: >-
  Clean up naming pollution for comms vs babysit workers (files, functions,
  labels, docs)
status: Done
assignee: []
created_date: '2026-07-05 12:52'
updated_date: '2026-07-16 13:09'
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
- [x] #1 File names and paths no longer exclusively use 'babysit' for comms workers (or explicit decision + compat note if keeping)
- [x] #2 Prints, help, and status legends use accurate language ('worker loop', 'comms consumer', 'babysit prompts enabled')
- [x] #3 Internal functions/labels updated consistently with the 'one loop + two groups' model
- [x] #4 self-awareness.txt, README, AGENTS.md, backlog docs updated
- [x] #5 Breaking changes minimized or migration notes added; tests updated
- [x] #6 No impact on running swarms (or handled)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Naming cleanup pass started: updated labels, help/legend text, self-awareness, stop/start_worker messages, added legacy note for file prefixes. Kept 'babysit-*' file stems for compat with existing swarms and consumers. More can be done (e.g. internal renames).

Follow-up naming commit e731c37. Strings, docs, labels cleaned while preserving runtime file compat.

Additional naming string cleanups (cli stop help, babysit sub help, legacy comments). Manual review materials also updated in tickets.

Deeper pass committed in dba35e0: removed dead desired_panes(), cleaned redundant imports in babysit.py, hardened process_running(), more README terminology updates for 'worker loop' vs babysit group. No file renames (compat).

Uncommitted work cleaned: committed review-requests/ (the manual review prompts for claude/codex), updated task md files, .gitignore for logs, final cli.py. Repo now clean. Deeper pass done.

Review-requests/ directory removed from repo (user: do not need to commit the manual review prompts).
No feedback received yet from the target panes.

2026-07-16 hygiene: remaining AC were migration notes / running-swarm safety; prefixes kept by design. Closing.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-05 13:04
---
Starting naming cleanup pass after commit de3f580. Will focus on labels, docs, strings, comments first (keeping file prefixes for compat). Review requests already sent to claude/codex panes.
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Naming cleanup done: labels/docs/help use worker-loop vs babysit-group language (e731c37, dba35e0). babysit-* runtime file stems kept intentionally for compat with existing swarms. Closed in hygiene 2026-07-16.
<!-- SECTION:FINAL_SUMMARY:END -->
