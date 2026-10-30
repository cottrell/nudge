---
id: TASK-90
title: 'Fix agy quota capture for separate Gemini, Claude/GPT, and Argon windows'
status: Done
assignee:
  - 'aiswarm:nudge:0.2'
created_date: '2026-10-22 12:32'
updated_date: '2026-10-30 11:25'
labels: []
dependencies: []
references:
  - swarm/usage/agy.sh
  - swarm/common.py
  - swarm/QUOTA_TRACKING.md
  - pane_worker.py
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
agy 1.4.3 /usage on a Google AI Pro account is a 38-line pager with three quota groups. Current sampling only keeps the first screen and then misreads the numbers, so status, forecast, and babysit pacing cannot tell Gemini, Claude/GPT, and Argon apart.

Observed on 2026-10-22 in a temporary agy session (live nudge pane 0.4 had the same overlay open):

- GEMINI MODELS (Gemini Flash, Gemini Pro): weekly 8.17% remaining, refreshes in about 33h; five-hour 94.11% remaining, refreshes in minutes.
- CLAUDE AND GPT MODELS (Claude Opus, Claude Sonnet, GPT-OSS): weekly and five-hour both 100% with the line "Quota available".
- GEMINI 4 ARGON: header does not end in MODELS. Pro copy says Argon quota is separate. Ultra copy says a higher Argon quota is included in the larger Gemini bucket. This account showed only "Gemini 4 Argon Weekly Limit" at 61.43% remaining, refreshes in about 49h. No five-hour line.

swarm/usage/agy.sh returns on the first percent sign. The cache at /tmp/nudge-usage-cache.json from 13:25 that day ended after the Gemini five-hour bar. The pager footer on a normal pane was "(1–5 of 38 lines)".

parse_agy_usage in swarm/common.py only splits headers that end in MODELS, so GEMINI 4 ARGON never becomes a group. The limit regex allows three words before Limit, and "Gemini 4 Argon Weekly Limit" has four, so that percent is dropped. Bars are labeled Limit Remaining, but the fallback treats the percent as used and stores 100 minus that percent. "Quota available" is hardcoded as exhausted, so a full Claude/GPT window becomes 0%. A recognized header is prefixed gemini when the name contains gemini, otherwise claude_gpt. Babysit in pane_worker.py takes min() across every agy limit, so one bad 0% slows every antigravity pane.

Init is out of scope. antigravity:heavy, medium, and light in swarm/models.yaml all launch gemini-3.8-flash. There is no init flavour for Argon or Claude/GPT on agy.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A full /usage capture includes Gemini, Claude/GPT, and Argon, not only the first screen
- [x] #2 Remaining percents match the Limit Remaining bars: 8.17 stays about 8, and 100% with Quota available is not stored as exhausted
- [x] #3 Argon weekly is its own limit and is not dropped or folded into the Gemini or Claude/GPT windows
- [x] #4 Babysit pacing for an antigravity pane does not treat another family's full or empty window as that pane's quota
- [x] #5 Tests cover this /usage shape, including the Argon header and Quota available
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. swarm/usage/agy.sh: capture the whole /usage overlay, not the first screen. After render, read the pager footer (N of M lines), page down with tmux-send and accumulate deduped lines until the footer reaches M or output stops changing; print the joined text.
2. swarm/common.py parse_agy_usage: (a) split group headers on all-caps headers generally, not only those ending in MODELS, so GEMINI 4 ARGON becomes a group; (b) widen the limit-label regex past three words so 'Gemini 4 Argon Weekly Limit' is kept; (c) bars are labelled 'Limit Remaining', so read the percent as remaining instead of inverting; (d) 'Quota available' means a full window -> 100 remaining, no reset, not Exhausted; (e) prefix limits gemini_/claude_gpt_/argon_ by group.
3. pane_worker._quota: filter agy limits to the pane's own model family before min(), so another family's full or empty window cannot pace the pane. Needs the pane command in the babysit spec (babysitctl.desired_spec).
4. test_swarm.py: fixture of the real 38-line /usage capture (Gemini 8.17 weekly + 94.11 five-hour, Claude/GPT 100% Quota available, Argon weekly 61.43, no Argon five-hour) covering parse and the pacing filter.
Note: make test is currently red from pane 0.4's in-flight TASK-92 work (swarm/models.py relative import vs flat import in swarm/topology.py); run targeted tests and re-check at the end.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified by running swarm/usage/agy.sh live on 2026-10-30: the capture now holds all three groups (GEMINI MODELS, CLAUDE AND GPT MODELS, GEMINI 4 ARGON) in 39 lines instead of the first 10. Fix for the pager was a tall temp session (-x 200 -y 80) plus a settle wait, not paging keys. parse_agy_usage rewritten line-oriented: unindented upper-case headers (so GEMINI 4 ARGON is a group), any word count before 'Limit', bar percent read as remaining, 'Quota available' -> 100 with no reset, prefixes gemini_/claude_gpt_/argon_. Live parse: gemini_weekly 53, gemini_five_hour 92, claude_gpt_* 100, argon_weekly 0 (refresh in 73h 58m, no five-hour line). pane_worker._own_family_limits filters agy limits to the pane's family before min(), using the new 'command' key in the babysit spec; the live argon_weekly 0% would otherwise have pinned every antigravity pane to exhausted. Fixture fixtures/agy_usage_capture.txt is the real capture with the account email scrubbed. make test: 184 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
agy /usage now captures and parses all three quota families. Scraper uses a tall temp tmux session so the 38-line overlay is not paged; parse_agy_usage reads 'Limit Remaining' bars as remaining, keeps GEMINI 4 ARGON as its own group, and treats 'Quota available' as a full window; babysit paces each antigravity pane from its own family only. Verified with a live agy.sh run and 4 new tests over a real capture fixture; make test 184 passed.
<!-- SECTION:FINAL_SUMMARY:END -->
