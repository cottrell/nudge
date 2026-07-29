---
id: TASK-53
title: 'monitor.c: log query overflows RESP_MAX response buffer (verified OOB write)'
status: To Do
assignee: []
created_date: '2026-07-29 15:48'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In handle_query the "log" branch accumulates n += snprintf(...) over up to 50 escaped lines. snprintf returns the WOULD-BE length, so n can exceed cap (RESP_MAX = MAX_LINE*55 = 56320). Once n > cap, out+n points past the static buffer and cap-n goes negative (converted to a huge size_t), so later snprintf calls and resp[rlen++]="\n" plus write(conn, resp, rlen) read/write out of bounds. Verified empirically (Fable 5 review 2026-07-29): feeding 60 lines of ~1000 control chars (each escapes to 6 bytes as \u00XX) and querying "log" returned a 102,460-byte response from the 56,320-byte buffer — silent BSS corruption, no crash. Any ANSI-heavy TUI pane (all agent CLIs) can trigger this via the log command on the unix socket or HTTP /log. Fix: clamp accumulation (break when n >= cap-margin, or track remaining capacity from the actual bytes written via return-value min(ret, remaining)), and size RESP_MAX for worst case or reduce lines returned. Same latent pattern: rlen from handle_query must never exceed RESP_MAX-1 before appending the newline.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 log query on a pane whose 50 buffered lines are each ~1000 control chars returns a response no larger than the buffer and valid JSON (possibly fewer lines)
- [ ] #2 test_monitor.py regression test feeds long control-char lines and asserts response size bound and monitor stays alive
- [ ] #3 status and tail branches audited for the same snprintf-return accumulation pattern
<!-- AC:END -->
