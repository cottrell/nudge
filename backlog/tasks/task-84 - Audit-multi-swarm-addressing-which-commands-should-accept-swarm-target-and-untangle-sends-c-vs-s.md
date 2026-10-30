---
id: TASK-84
title: >-
  Swarm selection: unify -c / -s / swarm: prefix (single-swarm commands); note
  true two-swarm ops are future
status: Done
assignee:
  - '@antigravity'
created_date: '2026-10-02 09:50'
updated_date: '2026-10-30 11:46'
labels:
  - cli
  - comms
dependencies: []
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Think/decide first; nothing here is built.

Correction to earlier framing: nothing today is truly multi-swarm. Every command acts on exactly ONE swarm, chosen by one of: -c/--config-file (or legacy positional config path), $AISWARM_CONFIG, cwd walk-up of .aiswarm/config.yaml, or, for send only, -s/--swarm / '<swarm>:<target>' prefix. -c already lets any command act on any swarm. -s and the prefix are a convenience for when you know the session name but not the config path: they read /tmp/nudge-swarm/<swarm>/runtime.json (target must be running; no config is loaded, so -c is silently ignored if both are given).

Problems to settle:
1. Two selectors doing the same job on send; -c silently ignored when -s/prefix is present. Decide: keep both and error on conflict, or drop one.
2. Only send accepts the name-based selector. capture/wait/status/log/sessions could accept it cheaply (read-only, same resolver); a shared helper (name -> session + runtime map) would serve all.
3. Sender attribution outside tmux: _infer_sender uses the real tmux pane when in tmux (fine). Outside tmux, 'send -c other' yields sender 'other:cli' (the TARGET's name, misattributed); '-s other' falls back to the local walk-up config (correct). Minor; fix when touching the resolver.
4. Danger rule: destructive/broad commands (clear, clear-comms, stop, broadcast, tasks, babysit) must never gain an implicit or default remote target. If ever selectable by name, require an explicit flag, no bare 'swarm:' prefix, plus confirmation.

Future, NOT needed now: genuinely two-swarm operations that hold knowledge of both swarms at once (two configs): e.g. cross-swarm send with sender identity from A, target validation from B, reply routing back to A; moving tasks between swarms; combined status. Revisit only if a concrete use appears.

Related: TASK-83 (CLI hierarchy), TASK-81 (qualified addressing, done).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decide: single remote selector (qualified prefix vs -s), and document that -c means the local swarm only
- [x] #2 Decide which commands get swarm:target support; destructive ones (clear, clear-comms, stop, broadcast, tasks, babysit) stay local or need explicit confirm
- [x] #3 Decide whether cross-swarm sends carry sender attribution (session:pane) and how replies route
- [x] #4 If yes to changes: one shared resolver helper, tests for -c/-s conflicts and for destructive commands refusing implicit remote targets
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extract / create a clean runtime lookup helper resolve_running_swarm(name) that loads /tmp/nudge-swarm/<name>/runtime.json or errors.
2. In cli.py:
   - For send / unsend: support <swarm>:<target> as the primary remote addressing; reject conflict if both remote target and -c are passed. Deprecate/keep -s as secondary alias pointing to the same resolver.
   - For capture: accept <swarm>:<pane>; if given, resolve via target swarm session name directly without needing -c.
   - For wait: accept <swarm>:<pane>; if given, resolve via target swarm session name directly.
   - For status: accept optional target swarm name or config path (aiswarm status <swarm>).
3. Update tests:
   - Verify capture <swarm>:<pane> works on another swarm without -c.
   - Verify wait <swarm>:<pane> works on another swarm without -c.
   - Verify send <swarm>:<target> with conflicting -c errors cleanly.
   - Verify status <swarm> works.
4. Run full test suite and request pane 0.5 (Grok) review via aiswarm send.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented unified remote addressing across capture, wait, and send. Conflicting -c with remote qualified targets raises an error. Peer reviewed by Grok in pane 0.5; addressed edge cases around conflict assertions, missing runtime error reporting, conflicting -s flags, and multi-window pane distribution in config_from_runtime_json. 185 tests in make test passing.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Unified remote addressing in aiswarm so <swarm>:<pane> works on capture, wait, and send using runtime.json without requiring -c. Rejects conflicting -c or conflicting -s flags. Peer-reviewed by Grok in pane 0.5. Verified by test_cli_qualified_capture_and_wait and full make test suite.
<!-- SECTION:FINAL_SUMMARY:END -->
