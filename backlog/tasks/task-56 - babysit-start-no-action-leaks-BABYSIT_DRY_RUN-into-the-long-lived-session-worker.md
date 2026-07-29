---
id: TASK-56
title: >-
  babysit start --no-action leaks BABYSIT_DRY_RUN into the long-lived session
  worker
status: Done
assignee:
  - 'aiswarm:nudge:0.3'
created_date: '2026-07-29 15:49'
updated_date: '2026-07-29 16:12'
labels: []
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py sets os.environ["BABYSIT_DRY_RUN"]="1" for --no-action, but the flag only has an effect if THIS invocation happens to spawn the session worker (Popen inherits env). Two failure modes: (a) if the worker is already running, --no-action silently does nothing; (b) if this call spawns the worker, the env var lives for the worker lifetime, so a later plain `babysit start` (or `tasks start`) sees the pid alive, returns early, and all prompt/comms delivery stays disabled with no indication — _deliver/_send_message in pane_worker check the env on every send. The simulate flag must be carried in the per-pane spec json (like via_log) or a runtime flag file the worker re-reads, not process env; and turning it off must not require killing the worker.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 no-action mode is honored regardless of whether the worker was already running
- [x] #2 plain babysit start after a --no-action start restores real delivery without manually killing session_worker
- [x] #3 status surfaces when the worker is in no-action/simulate mode
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fix implemented: Move BABYSIT_DRY_RUN flag from process environment to per-pane spec JSON.

**Changes made:**

1. **babysitctl.py**:
   - Added 'simulate' parameter to desired_spec() (default False)
   - Updated _wanted() to pass simulate=no_action to desired_spec()
   - Updated _apply() to accept no_action parameter
   - Updated apply_babysit() to accept no_action and display 'simulate mode' in label

2. **cli.py**:
   - Removed os.environ["BABYSIT_DRY_RUN"] = "1" assignment
   - Now passes no_action flag directly to apply_babysit()

3. **pane_worker.py**:
   - _send_message() now checks simulate parameter, not env var
   - _drain_comms() accepts and passes simulate parameter
   - _deliver() accepts and passes simulate parameter  
   - tick() extracts simulate from spec and passes to all comms calls

4. **topology.py**:
   - status_lines() now displays '(simulate)' when spec.simulate=True

**Key insight**: The spec JSON is re-read every tick (~1s) by the worker loop, so changing simulate mode doesn't require worker restart.

**Testing**: All acceptance criteria verified with workflow tests.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: aiswarm:nudge:0.4
created: 2026-07-29 16:12
---
## Peer review (aiswarm:nudge:0.4 / antigravity)
Verdict: APPROVE
ACs:
- AC #1 (no-action mode honored regardless of worker running status): Holds. The simulate/dry-run flag is decoupled from the process environment variables and stored directly in the per-pane spec JSON files. Updates write to disk and the worker loads the spec on every tick.
- AC #2 (plain babysit start restores delivery without kill): Holds. Re-running without `--no-action` writes `simulate: false` to the spec files. The multiplexing supervisor detects the file modification time (`mtime_ns`) change, re-loads the spec, and dynamically toggles simulate mode off.
- AC #3 (status surfaces simulate mode): Holds. `topology.status_lines` inspects the active spec and appends `(simulate)` to the status.

Findings:
- The implementation of `load_spec` utilizing `st_mtime_ns` file cache gating is clean and ensures CPU efficiency while allowing instantaneous updates.
- Decoupling environment variables from the long-lived process resolves the environmental state leak cleanly.

Residual risks:
- None identified. Tested and verified.
---
<!-- COMMENTS:END -->
