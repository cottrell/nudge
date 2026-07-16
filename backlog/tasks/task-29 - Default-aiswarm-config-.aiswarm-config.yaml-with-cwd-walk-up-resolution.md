---
id: TASK-29
title: 'Default aiswarm config: .aiswarm/config.yaml with cwd walk-up resolution'
status: Done
assignee:
  - grok
created_date: '2026-07-16 09:41'
updated_date: '2026-07-16 09:44'
labels: []
dependencies: []
references:
  - task-27
modified_files:
  - swarm/common.py
  - swarm/cli.py
  - swarm/init.py
  - test_swarm.py
  - README.md
  - AGENTS.md
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Consumer projects (and eventually this implementer repo's harness) should use a hidden harness dir, not a path you type every time.

Convention (git-like walk-up):
- Default file: `.aiswarm/config.yaml`
- Discover by walking up from cwd (and optionally from $PWD)
- Override: explicit path argument, or `AISWARM_CONFIG` env
- `aiswarm init` writes `.aiswarm/config.yaml` + prompts (not `./swarm/<name>.yaml`)

This repo (`nudge`) IMPLEMENTS aiswarm: `./swarm/` is package code. Harness today is `./nudgeswarm/` — do not break the live session here. Dogfood on another repo first. Optional later: compat for `nudgeswarm/nudge.yaml`.

Out of scope: TASK-28 instructions surface; renaming /tmp/nudge-swarm runtime prefix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 resolve_config finds .aiswarm/config.yaml by walking up from cwd
- [x] #2 AISWARM_CONFIG env and explicit path override discovery
- [x] #3 CLI subcommands that need a config work with no path when default exists
- [x] #4 aiswarm init creates .aiswarm/config.yaml (and prompts) not swarm/<name>.yaml
- [x] #5 Backwards-compatible: explicit path still works (e.g. nudgeswarm/nudge.yaml)
- [x] #6 Tests cover discovery, env override, init layout
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add resolve_config_path in common.py (explicit > AISWARM_CONFIG > walk-up .aiswarm/config.yaml).
2. Wire CLI: optional config args; send/broadcast/capture keep BC for old positional form.
3. Change init to write .aiswarm/; update Next: hints and AGENTS block lightly.
4. Tests + brief README note. Do not migrate this repo's live nudgeswarm/ yet.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented resolve_config_path + CLI optional config + init writes .aiswarm/. Tests pass. This repo still uses explicit nudgeswarm/ for live session.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Default config: .aiswarm/config.yaml via cwd walk-up; $AISWARM_CONFIG and explicit path override. init writes .aiswarm/ + gitignore. CLI optional config on all swarm commands; send/broadcast/capture keep legacy positional form. This repo live harness unchanged (nudgeswarm/). 45 tests pass. aiswarm reinstalled editable.
<!-- SECTION:FINAL_SUMMARY:END -->
