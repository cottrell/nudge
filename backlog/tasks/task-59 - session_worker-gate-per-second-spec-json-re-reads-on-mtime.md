---
id: TASK-59
title: 'session_worker: gate per-second spec/json re-reads on mtime'
status: In Progress
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-29 15:49'
updated_date: '2026-07-29 15:56'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a small pane-spec loader that stats each path but only reads/parses JSON when the nanosecond mtime changes.
2. Use the cached loader in both session_worker per-pane loading and legacy pane_worker.main, while preserving live spec reload behavior.
3. Add regression coverage for unchanged and changed specs, run focused/full tests, then record AC evidence and finalize.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.0 (session nudge).
<!-- SECTION:NOTES:END -->
