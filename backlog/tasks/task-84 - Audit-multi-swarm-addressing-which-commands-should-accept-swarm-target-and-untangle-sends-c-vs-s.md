---
id: TASK-84
title: >-
  Audit multi-swarm addressing: which commands should accept swarm:target, and
  untangle send's -c vs -s
status: To Do
assignee: []
created_date: '2026-10-02 09:50'
labels:
  - cli
  - comms
dependencies: []
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Think/decide first. Findings from a read of swarm/cli.py (send path ~line 985-1040):

1. Only 'send' is multi-swarm today (-s/--swarm SWARM, or qualified '<swarm>:<target>'). It resolves the target swarm via /tmp/nudge-swarm/<swarm>/runtime.json. Every other command (broadcast, clear, capture, wait, status, log, sessions, stop, babysit, tasks) is local-only and picks its swarm via -c/--config-file, $AISWARM_CONFIG or cwd walk-up. Several also accept a legacy positional config path.

2. send has TWO swarm selectors with different meanings: -c picks the LOCAL config (sender identity, local target validation); -s / 'swarm:' picks the REMOTE target swarm. Once a swarm is named, the config is not loaded and -c is silently ignored. -s is effectively sugar for the 'swarm:target' prefix. Cross-swarm sends also lose sender attribution: _infer_sender(None) is used when swarm_name is set, so the receiver may not see which swarm/pane sent it. Confusing and easy to misuse (e.g. -c other.yaml -s foo).

3. Danger asymmetry: delivering text is low risk, but destructive/broad commands must NOT become multi-swarm by default: clear (/clear wipes agent context), clear-comms (wipes event log), stop, broadcast (fan-out), tasks start/stop, babysit. Requiring an explicit qualified target or a --swarm flag for these, never inferred or defaulted, is the safe rule.

Candidate classification (strawman):
- Read-only, safe to qualify: capture, wait, status, log, sessions (swarm:pane or --swarm)
- Message-sending, qualify OK: send (already), healthcheck pong
- Destructive/broad: clear, clear-comms, stop, broadcast, tasks, babysit -> local only; if ever remote, require explicit --swarm AND a confirm or --yes, never a bare 'swarm:' prefix
Questions to settle: one shared resolver (swarm name -> session, runtime map, config-less) used by all commands; drop -s in favor of the qualified prefix only (or make -s the single remote selector and say -c is local-only); whether remote sends should carry sender '<mysession>:<pane>' so replies work; related to TASK-83 (CLI hierarchy) and the swarm:pane wait/capture idea.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide: single remote selector (qualified prefix vs -s), and document that -c means the local swarm only
- [ ] #2 Decide which commands get swarm:target support; destructive ones (clear, clear-comms, stop, broadcast, tasks, babysit) stay local or need explicit confirm
- [ ] #3 Decide whether cross-swarm sends carry sender attribution (session:pane) and how replies route
- [ ] #4 If yes to changes: one shared resolver helper, tests for -c/-s conflicts and for destructive commands refusing implicit remote targets
<!-- AC:END -->
