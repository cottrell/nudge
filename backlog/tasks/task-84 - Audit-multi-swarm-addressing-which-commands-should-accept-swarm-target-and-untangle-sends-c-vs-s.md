---
id: TASK-84
title: >-
  Swarm selection: unify -c / -s / swarm: prefix (single-swarm commands); note
  true two-swarm ops are future
status: To Do
assignee: []
created_date: '2026-10-02 09:50'
updated_date: '2026-10-02 09:54'
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
- [ ] #1 Decide: single remote selector (qualified prefix vs -s), and document that -c means the local swarm only
- [ ] #2 Decide which commands get swarm:target support; destructive ones (clear, clear-comms, stop, broadcast, tasks, babysit) stay local or need explicit confirm
- [ ] #3 Decide whether cross-swarm sends carry sender attribution (session:pane) and how replies route
- [ ] #4 If yes to changes: one shared resolver helper, tests for -c/-s conflicts and for destructive commands refusing implicit remote targets
<!-- AC:END -->
