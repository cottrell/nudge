---
id: TASK-82
title: 'Add aiswarm send --at: scheduled message delivery via comms loop'
status: Done
assignee:
  - '@antigravity'
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 09:39'
labels:
  - comms
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Allow deferring a message: 'aiswarm send --at <ISO time|+2h|+30m> <target> "msg"'. Store the event in the comms events log with a not-before timestamp; the comms loop (session worker) delivers it only once the clock has passed it AND the normal delivery conditions hold (pane idle, etc). Works for pane, category, 'any' and qualified targets. No backlog task is involved; this is for reminders/nudges. Related: TASK-64 (parked: scheduling backlog tasks). Keep it cheap: add a nullable not_before column (migrate existing events table in swarm/common.py) and skip rows with not_before > now in delivery, claim_any and cursor fan-out paths.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 send accepts --at with ISO timestamp and relative +Nh/+Nm/+Ns; invalid values error clearly
- [x] #2 Events table gains nullable not_before; existing DBs migrate in place
- [x] #3 Delivery, claim_any and broadcast/cursor fan-out skip not-yet-due events and do not block later due events (no head-of-line blocking)
- [x] #4 Not-yet-due messages are visible in log/status output with their due time
- [x] #5 Tests: future message not delivered, delivered after due, any/category targets, no head-of-line blocking; make test passes
- [x] #6 Documented in aiswarm instructions and README
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Implement parse_at_spec in swarm/common.py for ISO timestamp and relative +Nh/+Nm/+Ns, raising clear ValueError on invalid inputs.
2. In swarm/common.py init_comms_db, add nullable not_before DATETIME column to events, create cursor_acks table, and migrate existing DBs in place via ALTER TABLE if column is missing.
3. Update log_send, log_any, and log_broadcast to store not_before column (and meta['not_before']).
4. Update claim_any, get_pending_events, get_pending_broadcasts, get_pending_any to skip not-yet-due events without head-of-line blocking, and record acks in cursor_acks.
5. In swarm/cli.py, add --at flag to send parser, validate with parse_at_spec, pass not_before to log_send/log_any, and show at timestamp in dry-run/sent output.
6. In swarm/topology.py, format due time in _print_log_event, show scheduled messages in status_lines, and show not-yet-due pending events in print_log(--pending).
7. In pane_worker.py, ensure per-message cursor advancement so delivered events are acknowledged immediately.
8. Update README.md and swarm/instructions.py with aiswarm send --at documentation and examples.
9. Add unit and end-to-end tests covering all acceptance criteria, run make test, and verify green.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added parse_at_spec supporting relative +Nh/+Nm/+Ns and ISO timestamps. Migrated events schema in place with nullable not_before and created cursor_acks table. Updated delivery loop, claim_any, and broadcast cursor fan-out to skip not-yet-due messages without head-of-line blocking. Exposed scheduled messages in status and log with due times. Updated instructions and README. Verified with 7 new tests and full test suite (make test green).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented aiswarm send --at for scheduled message delivery. Commits: b84502f. Verified with make test (30 monitor + 161 swarm tests passing).
<!-- SECTION:FINAL_SUMMARY:END -->
