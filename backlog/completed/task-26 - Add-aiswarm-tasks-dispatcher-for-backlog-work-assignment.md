---
id: TASK-26
title: Add aiswarm tasks dispatcher for backlog work assignment
status: Done
assignee: []
created_date: '2026-07-15 12:42'
updated_date: '2026-07-15 12:46'
labels:
  - swarm
  - tasks
  - backlog
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Session-level free poller that lists backlog tasks (ingest statuses from YAML, default To Do only) and assigns them to idle panes with nudge.tasks.enabled via the durable log. Separate from babysit. Source flavor is backlog for v1; name is tasks so other sources can be added later.

Why: avoid wasting agent tokens on fixed continue-nudges when real work lives in backlog. Orchestrator must interact with backlog itself (claim before send); agents only get a concrete task prompt when free.

CLI:
  aiswarm tasks start ./swarm/foo.yaml
  aiswarm tasks stop ./swarm/foo.yaml
  aiswarm tasks status ./swarm/foo.yaml
  aiswarm tasks once ./swarm/foo.yaml   # optional single pass

Config (session):
  tasks:
    source: backlog
    backlog_dir: ./backlog   # required or default relative to yaml
    ingest: [To Do]         # optional In Progress etc
    poll_secs: 60
    require_label: null
    unassigned_only: true
    claim_assignee_prefix: aiswarm

Config (pane):
  nudge.tasks.enabled: true
  (mutually exclusive with babysit.enabled by convention; warn if both)

v1 behavior:
- One dispatcher process per swarm
- Poll backlog via CLI with cwd = project root containing backlog_dir
- Claim: status In Progress + assignee aiswarm:<session>:<pane> before log_send
- Deliver via log_send; completion is agent/human via backlog (not idle detection)
- Idle gate via monitor socket when available
- Local state under /tmp/nudge-swarm/<session>/tasks/
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 CLI: aiswarm tasks start|stop|status|once with YAML config
- [x] #2 Session tasks config: source, backlog_dir, ingest, poll_secs, require_label, unassigned_only
- [x] #3 Per-pane nudge.tasks.enabled; warn if babysit also enabled on same pane
- [x] #4 Dispatcher claims task (In Progress + assignee) before log_send to idle pane
- [x] #5 Default ingest is To Do only; In Progress opt-in via YAML
- [x] #6 stop swarm also stops tasks dispatcher
- [x] #7 Unit tests for config parse, claim prompt, and once dry-run
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
v1 implemented [Grok/xAI]: aiswarm tasks start|stop|status|once; TasksSpec in common; swarm/tasksctl.py + tasks_dispatch.py; claim before log_send; default ingest To Do; swarm stop stops dispatcher; tests in test_swarm.py; README section.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
v1: aiswarm tasks dispatcher pulls backlog work (ingest default To Do), claims before log delivery to free panes with nudge.tasks.enabled. Separate from babysit. Name is tasks for future non-backlog sources.
<!-- SECTION:FINAL_SUMMARY:END -->
