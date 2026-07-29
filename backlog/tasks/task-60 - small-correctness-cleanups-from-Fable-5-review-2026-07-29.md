---
id: TASK-60
title: small correctness cleanups from Fable 5 review 2026-07-29
status: To Do
assignee: []
created_date: '2026-07-29 15:49'
labels: []
dependencies: []
priority: low
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Bundle of small verified nits, each too small for its own task. 1) babysitctl.stop_workers and tasksctl.status crash with uncaught ValueError if a pid file exists but is empty/garbage (int(path.read_text().strip())). 2) pane_worker: a babysit spec with only short_prompt (no long_prompt) never nudges — the startup branch sends long_prompt="" so next_nudge_at is never set; either fall back to short_prompt at startup or reject the config. 3) attach.sh comment block claims sockets are named /tmp/session_0-0.sock (dashes); code and Python produce _0.0.sock (dots) — fix the comment. 4) init.py writes start_directory: ./ into generated configs but load_config never reads it — dead key, remove or implement. 5) pane_worker treats state "rate_limited" as idle-like but monitor.c never emits it — vestigial, remove or document. 6) tasksctl.process_running returns False on PermissionError (live process owned by another user, relevant on this shared machine). 7) resolve_backlog_dir accepts an explicit dir without config.yml but walk-up requires config.yml — align validation. 8) cli.py quota-debug aliases list repeats the primary name.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 stop/status tolerate empty or garbage pid files
- [ ] #2 short-prompt-only babysit either nudges or fails config validation with a clear error
- [ ] #3 stale attach.sh socket-name comment fixed; dead start_directory and rate_limited references removed or implemented
<!-- AC:END -->
