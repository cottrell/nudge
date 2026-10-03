---
id: TASK-86
title: unsend sender-identity check can mismatch send
status: Done
assignee: []
created_date: '2026-10-03 11:54'
labels:
  - unsend
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
send infers sender via _infer_sender(session if not -s else None); ':cli' identities depend on cwd/config, so unsend could deny the original sender. Fixed by only denying when both identities are tmux panes (<sess>:W.P) and differ; --force overrides. Proper fix would be a stable sender identity (e.g. env var or explicit --sender) recorded at send.
<!-- SECTION:DESCRIPTION:END -->
