---
id: TASK-48
title: >-
  Rename babysit.py + collapse long-running Python processes (one session
  supervisor, not N pane workers)
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-27 12:15'
updated_date: '2026-07-27 12:17'
labels:
  - swarm
  - babysit
  - tasks
  - naming
  - process-model
dependencies: []
documentation:
  - doc-4
priority: high
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

1. **Naming**: `babysit.py` is a misleading legacy name. It is the **per-pane worker IO loop** (always: durable-log/comms delivery; optional: prompt-nudge group). Operators and agents keep asking "why is babysit running?" when they only started tasks/comms. TASK-13/15 already split the *control API* (comms vs babysit prompt group) but left the process filename as `babysit.py`.

2. **Process model is the real cost**: Today we spawn **one Python process per pane** via `babysitctl.ensure_workers` → `Popen([python, babysit.py, session:pane, ...])`. Live machine snapshot (2026-07-27):
   - **36** `babysit.py` processes across 6 swarms
   - **~2.3 GiB** total RSS (~70–100 MB each — not light)
   - **3** additional `tasks_dispatch.py` long-runners (~33–35 MB each)

That contradicts the design intent behind the **C `monitor`**: keep hot status detection cheap; Python should not multiply into a herd of interpreters.

## Why tasks_dispatch is separate (today)

Historical / modularity only, not a hard requirement:
- TASK-26: session-level free poller, deliberately "separate from babysit"
- `tasks_dispatch.py` is a tiny long-running loop (`while True: dispatch_once; sleep poll_secs`)
- Independent start/stop (`aiswarm tasks start|stop`) and its own pid under `/tmp/nudge-swarm/<session>/tasks/`

There is **no** strong reason it must be its own OS process. It does not need crash isolation more than the pane workers, and it already depends on the same config/runtime tree.

## Desired direction

### A. Rename (clarity, smaller blast radius)

Rename the process entrypoint so `ps` is self-explanatory.

Candidate names (pick one; avoid colliding with C `monitor` / `monitor-bin`):
- **`pane_worker.py`** (recommended) — matches "one IO loop per pane" docs
- `comms_worker.py` — accurate for default mode; underplays optional nudge group
- `nudge_worker.py` — ok, a bit vague
- **Avoid `nudge_monitor.py`** — clashes mentally with `monitor.c` (status sockets)

Also rename/control-plane cleanup as follow-through (can be same PR or stacked):
- `babysitctl.py` → `workerctl.py` (or keep module, re-export shims)
- CLI surface: keep `aiswarm babysit start|stop` as **prompt-group** commands; workers are started by `aiswarm start` / `ensure_workers`
- Docs/README/self-awareness: "worker process" vs "babysit prompt group" vs "tasks dispatcher"

### B. Process consolidation (the point of C monitor)

Ideal steady state **per swarm session**:

| Role | Process | Notes |
|------|---------|-------|
| Status scrape | C `monitor` (per pane or multiplexed) | Cheap; already the idle/busy source |
| Session supervisor | **1** long-running Python | Comms drain for all panes + optional prompt groups + **tasks dispatch** |
| Agents | agent CLIs in tmux | Not ours to merge |

Concretely:
1. Replace N× `babysit.py` with **one** `session_worker.py` / `swarm_supervisor.py` that multiplexes panes (per-pane state dict, shared poll sleep, existing log cursors).
2. Fold `tasks_dispatch` loop into that same supervisor (event group toggled by `aiswarm tasks start|stop` writing a flag/spec — same pattern as dynamic babysit enable).
3. Keep crash boundaries only where they earn it; default is fewer interpreters, not more.

### C. Out of scope / non-goals

- Do not reimplement status detection in Python (that is why `monitor.c` exists).
- Do not change durable log protocol or backlog claim semantics in the rename PR.
- Per-swarm isolation remains (one supervisor per session, not one global daemon for all machines' swarms).

## Acceptance criteria suggestions

- [ ] `babysit.py` renamed; no entrypoint left that shows as `babysit.py` in `ps`
- [ ] Docs + CLI help distinguish: worker process / babysit prompts / tasks
- [ ] Compat shim or one release note if external scripts invoke `babysit.py`
- [ ] Design note committed: one Python supervisor per session; tasks is a loop group not a process
- [ ] (Stretch / follow-on) N panes → 1 Python process; RSS scales with session count not pane count
- [ ] (Stretch) `tasks_dispatch.py` no longer a separate long-running process when supervisor is up

## Evidence / motivation

- Live: 36 pane workers + 3 tasks dispatchers while CPU of workers is ~0% — pure resident Python tax + swap pressure.
- TASK-13 user model already said "one IO loop"; we implemented one loop *per pane process*, not one loop for the session.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Rename babysit.py entrypoint to a name that reflects pane/session worker (prefer pane_worker.py or session_worker.py; avoid nudge_monitor.py clash with monitor.c)
- [x] #2 Update babysitctl/topology/tests/docs so ps, help, and self-awareness no longer imply workers are "babysit-only"
- [x] #3 Document process model: C monitor = status; ideally one long-running Python supervisor per session for comms + optional prompt group + tasks
- [x] #4 Write design note on folding tasks_dispatch into that supervisor (no separate long-running tasks_dispatch.py in the ideal model)
- [x] #5 Compat: old name shim or explicit break noted in changelog/README
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Rename the per-pane process entrypoint to pane_worker.py and update launch/test references without changing worker semantics.
2. Update operator-facing docs and CLI wording to distinguish pane workers, babysit prompt groups, and the separate tasks dispatcher.
3. Create a Backlog design note for the target one-supervisor-per-session model and document the explicit babysit.py compatibility break.
4. Run the swarm test suite and finalize the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.0 (session nudge).

Renamed the per-pane entrypoint to pane_worker.py and updated its launcher, integration test, operator docs, and instruction help. babysit.py is an explicit compatibility break documented in README/instructions. Added design note doc-4 for one session supervisor handling comms, optional prompt groups, and tasks dispatch. Validation: make test-swarm passed; make test-c passed on rerun after one unrelated Grok fixture timing failure.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Renamed the per-pane worker entrypoint to pane_worker.py, clarified worker versus babysit prompt-group terminology, and documented the one-supervisor-per-session target in doc-4. Verified swarm and monitor test targets pass.
<!-- SECTION:FINAL_SUMMARY:END -->
