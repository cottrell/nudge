---
id: TASK-87.1
title: >-
  Implement 'aiswarm presence' command with global and local scopes and passive
  tmux detection
status: Done
assignee:
  - '@antigravity'
created_date: '2026-10-09 10:40'
updated_date: '2026-10-09 10:46'
labels: []
dependencies: []
parent_task_id: TASK-87
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement presence detection and override CLI (`aiswarm presence [local|global] [mode]`). Uses stateless on-demand `tmux list-clients` inspection for passive auto detection, minimal JSON overrides in /tmp for pinned states, and clear effective-state reporting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 CLI command 'aiswarm presence' displays effective presence, local mode, and global mode with clear source attribution
- [x] #2 'aiswarm presence global in|out|auto' sets global override or resets to auto
- [x] #3 'aiswarm presence local in|out|auto|global' sets swarm-local override or defers to global
- [x] #4 Passive auto mode evaluates tmux list-clients client_activity against configurable idle timeout (default 15m)
- [x] #5 Unit tests cover presence evaluation (all mode combinations, overrides, thresholds, and missing clients)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Create `swarm/presence.py` module:
   - Data structures: GlobalPresence, LocalPresence, EffectivePresence
   - Passive inspection: run `tmux list-clients -F "#{client_session} #{client_activity}"`
   - Evaluate passive auto state based on idle_timeout (default 900s / 15m)
   - Store manual overrides as JSON:
     - Global override: `/tmp/nudge-swarm/presence_global.json`
     - Swarm-local override: `/tmp/nudge-swarm/<swarm>/presence_local.json`
   - Support `until` expiration timestamps for temporary leases
   - Resolution precedence: Local override (if not "global") -> Global override -> Auto
   - Format human-readable output and JSON output

2. Add CLI integration in `swarm/cli.py`:
   - Subcommand `presence`:
     - `aiswarm presence` -> displays effective presence, local mode, and global mode
     - `aiswarm presence global [in|out|auto]` (with optional `--for`)
     - `aiswarm presence local [in|out|auto|global]` (with optional `--for`, optional swarm / -c / -s)
     - Shorthand support: `aiswarm presence [in|out|auto|global]` defaults to local scope

3. Update docs & instructions:
   - Add presence section to `swarm/instructions.py` (or document in `overview`)
   - Update `AGENTS.md` and `README.md`

4. Write comprehensive tests in `tests/test_presence.py`:
   - Passive calculation from mocked `tmux list-clients`
   - Global in/out/auto overrides
   - Local in/out/auto/global overrides
   - Lease expiry (`until`)
   - Formatting & CLI roundtrips
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented presence detection and overrides in swarm/presence.py and swarm/cli.py. Added default 15m idle timeout without requiring config changes. Added instructions in swarm/instructions.py, README.md, AGENTS.md. Full test suite passed: make test (176 tests).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented 'aiswarm presence' command with global and local scopes, stateless passive tmux client idle evaluation (15m default), temporary leases (--for), and full test coverage in test_presence.py.
<!-- SECTION:FINAL_SUMMARY:END -->
