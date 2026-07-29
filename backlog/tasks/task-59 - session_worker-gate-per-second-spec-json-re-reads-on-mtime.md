---
id: TASK-59
title: 'session_worker: gate per-second spec/json re-reads on mtime'
status: To Do
assignee: []
created_date: '2026-07-29 15:49'
labels: []
dependencies: []
priority: low
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The supervisor loop re-reads and json-parses every pane spec file every second (session_worker.pane_spec) even though PaneWorker.tick throttles real work to a 5s poll, and calls babysit_runtime_paths twice per pane per tick. With 8 panes that is ~16 file reads + json parses per second forever. Cache parsed spec per pane keyed on stat mtime (like the existing config_mtime pattern in the same loop). Same pattern applies to pane_worker.main spec reload. Cheap, contained fix; measurable idle-CPU reduction for always-on swarms.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 spec files are re-parsed only when their mtime changes
- [ ] #2 behaviour identical when specs change on disk (existing spec-reload test still passes)
<!-- AC:END -->
