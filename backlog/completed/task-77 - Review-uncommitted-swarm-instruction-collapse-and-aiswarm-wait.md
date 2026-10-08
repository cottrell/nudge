---
id: TASK-77
title: Review uncommitted swarm instruction collapse and aiswarm wait
status: Done
assignee:
  - 'aiswarm:nudge:0.1'
created_date: '2026-09-18 12:07'
updated_date: '2026-09-18 12:08'
labels: []
dependencies: []
modified_files:
  - swarm/instructions.py
  - swarm/topology.py
  - swarm/cli.py
  - swarm/init.py
  - test_swarm.py
  - AGENTS.md
  - README.md
  - .aiswarm/prompts/worker_long.md
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Pane 0.5 (grok) collapsed swarm agent guides (dropped observe/handoff) and added `aiswarm wait` so a coordinator can block on monitor-idle or capture-pane stability instead of attaching/streaming. Work is uncommitted on main in ~/dev/nudge.

Reply-to pane: 0.5
On complete: notes + final-summary on this task, then `aiswarm send 0.5 "TASK-NN done"`.
TUI findings are not done.

Why: agents over-read "never attach/stream" as "never look at another pane", then dual-idled after TUI-only reviews. User asked to cut fake subsystems (observe/handoff/overview split) and put idle-wait in the controller.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Review git diff of uncommitted files (not HEAD-only): swarm/instructions.py, swarm/topology.py wait_pane, swarm/cli.py wait, swarm/init.py AGENTS block, test_swarm.py, AGENTS.md, README.md, .aiswarm/prompts/worker_long.md
- [x] #2 Call out bugs, missing tests, and instruction regressions (handoff protocol gone; wait-on-already-idle; --stable vs monitor idle; TUI-findings rule still load-bearing)
- [x] #3 Write findings as backlog notes + final-summary on this task (not only in the TUI)
- [x] #4 Ping pane 0.5 with aiswarm send when done
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review complete against the unstaged diff (all requested files).

Findings: no blocking bug found. wait_pane correctly returns immediately for monitor-idle, times out with status, rejects unknown panes, and --stable waits for unchanged capture text independently of monitor state. Existing tests cover those core paths and all tests pass.

Instruction review: TUI-findings-not-done remains load-bearing and is now present in generated AGENTS/prompts/overview. The dedicated handoff guide was removed from the guide index, but observe/handoff compatibility aliases remain and the longer backlog handoff doc remains discoverable from README. Risk: the detailed send -> backlog -> done-ping protocol is less discoverable from `instructions overview`; consider retaining a short protocol pointer if this is unintended.

Missing coverage: no direct CLI-level test for `wait` argument splitting/dispatch, and no explicit stable-capture failure/timeout test. These are follow-up test improvements, not blockers.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reviewed TASK-77 unstaged changes across swarm instructions, topology wait_pane, CLI, init templates, docs, prompt, and tests. No blocking defects found. Verified monitor-idle and capture-stability wait behavior, already-idle handling, timeout/unknown-pane paths, instruction regressions, and TUI findings rule. `make test` passed: 30 monitor tests and 127 swarm tests.
<!-- SECTION:FINAL_SUMMARY:END -->
