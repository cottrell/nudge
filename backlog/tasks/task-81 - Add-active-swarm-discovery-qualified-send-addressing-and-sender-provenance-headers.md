---
id: TASK-81
title: >-
  Add active swarm discovery, qualified send addressing, and sender provenance
  headers
status: Done
assignee:
  - '@antigravity'
created_date: '2026-10-02 09:09'
updated_date: '2026-10-02 09:16'
labels: []
dependencies: []
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agents and operators working across multiple swarms on one machine lack simple ways to discover active swarms and trace message origins during cross-swarm interactions. Adding lightweight inspection of /tmp/nudge-swarm, qualified swarm:target addressing in aiswarm send, automatic sender inference, and delivery envelope prefixes enables robust inter-swarm communication without requiring a central daemon.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 aiswarm swarms command inspects /tmp/nudge-swarm/*/runtime.json and lists sessions, pane counts, and active status
- [x] #2 aiswarm send supports qualified <swarm>:<target> syntax as shorthand for -s <swarm> <target>
- [x] #3 aiswarm send auto-populates sender identity from environment (tmux pane / session) when omitted
- [x] #4 comms delivery prepends an envelope prefix with sender name when delivering messages to tmux panes
- [x] #5 Tests verify swarms listing, qualified send addressing, sender inference, and delivery prefixing
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add 'aiswarm swarms' CLI command in swarm/cli.py and swarm/topology.py scanning /tmp/nudge-swarm/*/runtime.json to report active/inactive swarms and worker state.
2. Add qualified <swarm>:<target> syntax parsing to 'aiswarm send' as shorthand for -s <swarm> <target>.
3. Implement sender auto-inference in 'aiswarm send' using tmux session/pane when running in tmux, falling back to session:cli or cli send.
4. Update _drain_comms in pane_worker.py to format external/agent messages with 'aiswarm-send: from <sender>: <payload>' while preserving internal messages and /clear.
5. Update instructions and help text.
6. Add comprehensive unit tests in test_swarm.py covering listing, qualified addressing, sender auto-population, and delivery prefixing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented 'aiswarm swarms' discovery command, qualified <swarm>:<target> addressing shorthand in 'aiswarm send', automatic sender inference from tmux session/pane, and 'aiswarm-send: from <sender>: <msg>' delivery prefixing in pane_worker._drain_comms. Verified with live CLI execution and 151 tests passing in make test.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added active swarm discovery via 'aiswarm swarms' (with table, --brief, and --json output), qualified <swarm>:<target> send addressing syntax, auto-inferred sender identity from tmux environment, and delivery envelope prefixing. Verified all 151 tests in make test and live CLI runs.
<!-- SECTION:FINAL_SUMMARY:END -->
