---
id: TASK-16
title: >-
  Fix runtime.json 'babysit' advertisement and status reporting so UIs (thoth
  etc.) correctly detect active prompt loop vs configured
status: In Progress
assignee: []
created_date: '2026-07-05 12:52'
updated_date: '2026-07-05 12:55'
labels:
  - nudge
  - babysit
  - swarm
  - runtime
  - status
  - interop
dependencies:
  - TASK-13
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Observed: For council-data (session 'cd'), /tmp/nudge-swarm/cd/runtime.json advertises 'babysit' entries with has_long_prompt:true for panes even when no pids, no specs, no state files, and `aiswarm status swarm/cd.yaml` reports the session as 'missing' (or babysit not active).

Thoth UI (or similar consumers) sees the 'babysit' key in runtime.json (populated from yaml + 'not spec_file.exists()') and believes babysit is running, while actual status (pid check + running process + live spec content + 'Babysit' column: 'off'/'stopped'/'not started') says otherwise.

Root cause in build_runtime_map: the condition `if pane.babysit.enabled: ... if has_... or not spec_file.exists(): advertise` causes stale advertisement after worker stop (specs are unlinked on stop_worker).

Also, recent status column changes (Comms HB, Babysit on/off/not-started/drifted, separate Nudge/Clear) may have broken parsers in external UIs that looked for old strings like 'running', old worker column format, or presence of babysit pid without checking activity.

Tasks:
- Make runtime.json accurately reflect whether a babysit *prompt loop* is currently active (e.g. check for running pid + current spec has prompts, or a explicit 'babysit_active' flag).
- Consider adding a top-level 'workers' or per-pane 'worker' status summary in runtime.json for consumers.
- Ensure `status --brief` / full output and runtime stay in sync.
- Investigate/update any thoth or council-data code that parses this (but primary fix in nudge reporting).
- Add note or compat if needed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 runtime.json only advertises active 'babysit' info when a worker with prompts is actually running (pid + process + spec has prompts)
- [x] #2 For panes where babysit is configured in yaml but currently disabled (comms mode or stopped), either omit the babysit key or mark it clearly (e.g. 'babysit': {'enabled_in_config': true, 'active': false})
- [ ] #3 `aiswarm status` and runtime.json agree on babysit state for council-data/cd and similar swarms
- [ ] #4 External consumers like thoth no longer falsely report babysit 'running' when cli status shows off/stopped/not-started/missing
- [ ] #5 Tests cover runtime map content for babysit-enabled + stopped cases
- [ ] #6 No regression for cases where babysit is truly active
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Partial fix: build_runtime_map now always includes for config.enabled but has_* come from deployed spec (false when empty or absent). Combined with dynamic, disable will produce has=false + runtime update.

build_runtime_map now sets has_* from deployed spec content. Combined with hot-update in disable, future runtimes will reflect 'not active' for disabled babysit. Test for runtime map still passes.
<!-- SECTION:NOTES:END -->
