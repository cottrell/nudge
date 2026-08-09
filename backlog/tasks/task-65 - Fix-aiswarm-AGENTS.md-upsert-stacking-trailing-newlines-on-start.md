---
id: TASK-65
title: Fix aiswarm AGENTS.md upsert stacking trailing newlines on start
status: Done
assignee:
  - '@antigravity'
created_date: '2026-08-08 13:48'
updated_date: '2026-08-09 07:43'
labels:
  - aiswarm
  - agents.md
  - bug
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

`aiswarm` start/init rewrites `AGENTS.md` via `swarm/init.py` → `write_agents_block` → `upsert_agents_text`.

When an AISWARM block is followed by other content (almost always the Backlog.md managed guidelines block), the upsert is **not idempotent**: each call adds one more trailing newline at EOF. Dirty `AGENTS.md` (`+\n` only) appears across many repos after swarm start.

Root: join path uses `head.rstrip()`, `tail.lstrip("\n")`, `"\n\n".join(parts) + "\n"`, which changes the file even when the AISWARM body is unchanged, and accumulates EOF newlines.

## Reproduce

```python
from swarm.init import upsert_agents_text, agent_block
block = agent_block("demo")
text = "# Project\n\n" + block + "\n<!-- BACKLOG.MD GUIDELINES START -->\nx\n<!-- BACKLOG.MD GUIDELINES END -->\n"
for i in range(5):
    text, action = upsert_agents_text(text, block)
    # action stays "updated"; trailing NL count increases each pass
```

## Scope

- Fix `upsert_agents_text` (and any related start path) so identical block body ⇒ `unchanged` and no file write.
- Do not grow trailing newlines across repeated start/init.
- Leave Backlog-managed section intact.
- Add regression test in `test_swarm.py`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Repeated upsert/start with AISWARM + following Backlog block does not change AGENTS.md when AISWARM body is unchanged
- [x] #2 Repeated upsert does not increase trailing newline count at EOF
- [x] #3 Regression test covers AISWARM-then-Backlog layout and multi-pass stability
- [x] #4 aiswarm start/init still inserts or updates AISWARM block correctly when content actually changes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Modify upsert_agents_text in swarm/init.py to strip leading and trailing whitespace/newlines from head and tail sections when replacing or checking the AISWARM block, producing clean idempotency with a single trailing EOF newline.
2. Add regression test test_agents_block_upsert_idempotency_with_following_backlog_block in test_swarm.py.
3. Verify test suite with make test.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed upsert_agents_text in swarm/init.py and added regression tests in test_swarm.py. Passed 102/102 pytest tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Updated upsert_agents_text in swarm/init.py so repeated upserts with following blocks (like Backlog.md guidelines) do not stack trailing newlines or register spurious changes. Added regression test test_agents_block_upsert_idempotency_with_following_backlog_block in test_swarm.py and verified via make test (102 tests passed).
<!-- SECTION:FINAL_SUMMARY:END -->
