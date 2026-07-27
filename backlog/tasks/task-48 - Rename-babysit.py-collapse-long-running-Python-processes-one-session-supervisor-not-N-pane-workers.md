---
id: TASK-48
title: >-
  Rename babysit.py + collapse long-running Python processes (one session
  supervisor, not N pane workers)
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-27 12:15'
updated_date: '2026-07-27 12:44'
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
- [x] #1 ONE Python IO loop/supervisor process per swarm (tmux session), not one per pane
- [x] #2 Comms (durable log drain) for all panes runs inside that single process
- [x] #3 Optional babysit prompt group still per-pane config but served by the same supervisor
- [x] #4 tasks dispatch long-running loop lives in the same supervisor (no separate tasks_dispatch.py process when tasks started); once remains CLI-callable
- [x] #5 C monitor-bin remains per-pane for status; not reimplemented in Python
- [x] #6 ps/htop for a 6-pane swarm shows ~1 supervisor Python, not 6 pane workers (+ not an extra tasks_dispatch)
- [x] #7 Docs/doc-4 updated to reflect implemented target, not follow-on only
- [x] #8 When done or blocked: aiswarm send 0.5 with status summary (reply to grok on nudge:0.5)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) Keep pane_worker rename. 2) Implement one long-running Python session supervisor per swarm that multiplexes ALL panes: durable-log/comms drain + optional babysit prompt group per pane. 3) Fold tasks_dispatch loop into that same supervisor (aiswarm tasks start|stop toggles the group; dispatch_once stays callable for once). 4) Stop spawning N pane_worker processes; stop separate tasks_dispatch process when supervisor owns tasks. 5) C monitor-bin stays per-pane. 6) Restart/migrate live workers; prove with ps that one swarm => one Python supervisor. 7) Comms status back to requester pane nudge:0.5 (grok) via aiswarm send when done or blocked.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
REOPENED 2026-07-27 by grok on nudge:0.5 (human-directed). Prior close by Codex on 0.0 (commit 17a48e7 ~13:17) was incomplete: rename-only + doc-4, process model unchanged. Still N Python pane workers + separate tasks_dispatch. User direction: implement ONE Python IO loop per swarm (tmux session). Rename was fine as step 1; consolidation is required for Done, not follow-on.

Implemented the session-worker consolidation: controller writes per-pane specs but launches one session_worker.py; it multiplexes pane comms/babysit and polls the tasks enable flag. tasks start/stop now toggles that flag instead of launching tasks_dispatch.py.

Validation: make test passes (28 monitor + 72 swarm tests). Live migration of nudge retired exactly its six recorded legacy workers and produced one session_worker.py PID (3769391) for six panes; status reported all six panes through it. tasks group has an explicit enabled.json state and test verifies start/stop toggles it with no dispatcher PID.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented mandatory session-supervisor consolidation in b077450. Normal swarm startup now launches one session_worker.py that multiplexes durable-log drains and optional per-pane babysit specs; tasks start/stop toggles a group in that supervisor, while tasks once remains direct. C monitor-bin remains per pane. Migrated the live six-pane nudge swarm from six recorded legacy workers to one supervisor PID and verified status for all panes. make test passed (28 monitor tests, 72 swarm tests).
<!-- SECTION:FINAL_SUMMARY:END -->
