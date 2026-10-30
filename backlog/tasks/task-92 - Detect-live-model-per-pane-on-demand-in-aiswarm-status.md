---
id: TASK-92
title: Detect live model per pane on demand in aiswarm status
status: Done
assignee:
  - '@antigravity'
created_date: '2026-10-30 11:10'
updated_date: '2026-10-30 11:19'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agent models can be switched live in-session via /model or CLI commands, but aiswarm status currently only displays startup config titles. Swarm agents and users need accurate visibility into the actual model currently active in each pane.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 aiswarm status parses and displays the live detected model for supported agent TUIs (agy, claude, codex) when available
- [x] #2 Detection happens on-demand during status using existing captured pane buffer without extra polling
- [x] #3 Falls back gracefully to title/config or '-' if the model cannot be identified from the screen buffer
- [x] #4 Unit tests verify model extraction for agy, claude, and codex screen capture fixtures
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inspect capture formats for agy, claude, codex (and grok/aider if easy)
2. Implement live model parsing helper in swarm/ (e.g. swarm/live_models.py or in topology.py)
3. Integrate live model into aiswarm status (e.g. add a Model column or format into Target/Title/Model)
4. Add unit tests for screen capture fixtures across providers
5. Run test suite make test and verify aiswarm status output
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented live model extraction from on-demand screen captures in swarm/models.py with fallback to process tree / session jsonl metadata. Integrated into aiswarm status (both full table and --brief). Added test_live_models.py. All 186 unit tests and make test passing.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added on-demand live model detection to aiswarm status. Parses TUI status footers/headers for agy, claude, codex, grok, and aider, falling back to process argv/session metadata or '-'. Verified with test_live_models.py (5 tests) and full test suite (make test).
<!-- SECTION:FINAL_SUMMARY:END -->
