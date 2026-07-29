---
id: TASK-53
title: 'monitor.c: log query overflows RESP_MAX response buffer (verified OOB write)'
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-29 15:48'
updated_date: '2026-07-29 15:54'
labels: []
dependencies: []
modified_files:
  - monitor.c
  - test_monitor.py
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In handle_query the "log" branch accumulates n += snprintf(...) over up to 50 escaped lines. snprintf returns the WOULD-BE length, so n can exceed cap (RESP_MAX = MAX_LINE*55 = 56320). Once n > cap, out+n points past the static buffer and cap-n goes negative (converted to a huge size_t), so later snprintf calls and resp[rlen++]="\n" plus write(conn, resp, rlen) read/write out of bounds. Verified empirically (Fable 5 review 2026-07-29): feeding 60 lines of ~1000 control chars (each escapes to 6 bytes as \u00XX) and querying "log" returned a 102,460-byte response from the 56,320-byte buffer — silent BSS corruption, no crash. Any ANSI-heavy TUI pane (all agent CLIs) can trigger this via the log command on the unix socket or HTTP /log. Fix: clamp accumulation (break when n >= cap-margin, or track remaining capacity from the actual bytes written via return-value min(ret, remaining)), and size RESP_MAX for worst case or reduce lines returned. Same latent pattern: rlen from handle_query must never exceed RESP_MAX-1 before appending the newline.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 log query on a pane whose 50 buffered lines are each ~1000 control chars returns a response no larger than the buffer and valid JSON (possibly fewer lines)
- [x] #2 test_monitor.py regression test feeds long control-char lines and asserts response size bound and monitor stays alive
- [x] #3 status and tail branches audited for the same snprintf-return accumulation pattern
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Make handle_query track actual bytes and reserve space for valid JSON closure, with a final length clamp for all branches.
2. Add a Unix-socket regression using 50 long control-character lines, checking bounded valid JSON and liveness.
3. Run focused and full monitor tests, audit status/tail bounds, then record AC evidence and finalize.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.0 (session nudge).

Implemented complete-entry admission for log JSON: each escaped line is copied only if the separator, entry, closing ]}, and NUL fit. handle_query now clamps all branch return lengths to RESP_MAX-1, so the Unix socket newline remains in bounds. Audited status and tail: both perform a single snprintf; status is fixed-size, while tail uses a bounded 2048-byte escaped buffer against the 56320-byte response buffer, and the common return clamp protects their reported lengths.
Validation: uv run pytest test_monitor.py -q -> 29 passed. Warning-enabled compilation succeeded (pre-existing ignored-I/O and strncpy warnings only). Full make test passed test_c.sh and all 29 monitor tests; its unrelated test_swarm.py phase had 80 pass / 1 fail because concurrent swarm code no longer exports tasksctl.monitor_socket_path.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bounded log response construction to complete JSON entries with reserved closure space and clamped every handle_query result before socket newline append. Added a 50x1000-control-character regression that verifies the response stays within RESP_MAX, parses as JSON, and the monitor remains alive. All 29 monitor tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
