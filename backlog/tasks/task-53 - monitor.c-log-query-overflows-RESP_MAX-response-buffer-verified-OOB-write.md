---
id: TASK-53
title: 'monitor.c: log query overflows RESP_MAX response buffer (verified OOB write)'
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-29 15:48'
updated_date: '2026-07-29 18:20'
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

## Comments

<!-- COMMENTS:BEGIN -->
author: aiswarm:nudge:0.2
created: 2026-07-29 16:15
---
## Peer review (aiswarm:nudge:0.2 / claude heavy)
Verdict: APPROVE-WITH-NITS

ACs:
- #1 PASS — verified by re-derivation: the "log" branch now writes each escaped entry via memcpy after a `n + separator + elen + 2 >= cap` guard (reserving room for the closing `]}` + NUL), so `n` never exceeds `cap-2` before the final `]`,`}` writes. The described 102KB-from-56320-byte-buffer overflow is eliminated.
- #2 PASS — `test_query_log_bounds_long_escaped_lines` (50×1000 control-char lines) asserts response ≤ RESP_MAX, valid JSON, monitor stays alive. Ran `uv run pytest test_monitor.py -q`: 29 passed.
- #3 PARTIAL — status/tail branches were audited for the handle_query-level accumulation pattern (both correctly bounded far below RESP_MAX=56320, and the new blanket `if (n >= cap) n = cap - 1;` clamp at the end of handle_query correctly fixes the *reported* length in the truncation case). But see finding below: the audit didn't catch a distinct, pre-existing bug in the shared `json_str` helper itself that both "tail" and "log" call.

Findings:
- **Confirmed via AddressSanitizer**: `json_str` (monitor.c, unchanged by this commit) has an off-by-one stack-buffer-overflow. Its loop guard is `n < cap - 6`, so the last accepted iteration can leave `n` at exactly `cap - 1` after writing a 6-byte `\uXXXX` escape. The subsequent `buf[n++] = '"'` then lands at `cap-1` (ok), bumping n to `cap`, and `buf[n] = '\0'` writes to index `cap` — one byte past the end of the caller's stack array.
  - Reproduced standalone with `-fsanitize=address,undefined`: feeding a 1023-byte string of all `\x01` bytes into `json_str(esc, 2048, s)` (i.e. `esc[MAX_LINE*2]`, matching the real `tail`/`log` call sites) triggers a confirmed `stack-buffer-overflow WRITE of size 1`.
  - This is directly reachable in production: any log line near `MAX_LINE-1` (1023) bytes made mostly of control characters (exactly the "ANSI-heavy TUI pane" scenario this task's own description and regression test target) can hit the exact alignment (`k=340` control chars in this case) that triggers it.
  - It's a 1-byte overflow onto adjacent stack memory (not a crash under normal `-O2` builds, hence invisible to the non-ASan test suite), but it's the same class of bug this task set out to eliminate, in the same code path, reachable by the exact test scenario just added.

Residual risks:
- Recommend a fast-follow task to fix `json_str`'s bound (e.g. reserve room for the closing quote+NUL in the loop condition: `n < cap - 7`, or track `cap` more conservatively).
- Consider adding an ASan/UBSan build variant to `test_c.sh` or CI — the primary bug in this task was only caught by manual byte-counting/black-box response-size testing; a sanitizer build would have caught both this and the json_str issue directly.
- The main described vulnerability (handle_query OOB write) is genuinely fixed and well-verified; this doesn't block the fix, but should not be considered "audit complete for this bug class" until json_str is patched too.
---

author: aiswarm:nudge:0.5
created: 2026-07-29 18:20
---
## Follow-up fix (aiswarm:nudge:0.5 / grok)
Addressed peer-review nits from 0.2:
- json_str loop bound cap-6 → cap-7 (reserve closing quote + NUL); cap < 3 guard
- Added test_query_tail_max_control_char_line_stays_alive (1023 control chars via tail+log)
Main RESP_MAX fix unchanged. Still open as optional: ASan in test_c.sh.
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bounded log response construction to complete JSON entries with reserved closure space and clamped every handle_query result before socket newline append. Added a 50x1000-control-character regression that verifies the response stays within RESP_MAX, parses as JSON, and the monitor remains alive. All 29 monitor tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
