---
id: TASK-43
title: >-
  Please make sure that an agent knows it can unassign itself for a task that
  should be deferred until later. it is not great but we just run a task and can
  not do it yet so we just pop it back on the do later stack
status: Done
assignee:
  - 'aiswarm:nudge:0.3'
created_date: '2026-07-22 14:01'
updated_date: '2026-07-22 20:49'
labels: []
dependencies: []
---

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.3 (session nudge).

## Implementation

Enhanced task prompt instructions to make it clearer that agents can defer tasks by unassigning themselves.

### Changes made:

**Initial task prompt (new agents):**
- Expanded step 4 to explicitly show how to unassign: `backlog task edit TASK-ID -a ''`
- Added guidance that task returns to dispatch pool for other panes
- Mentioned option to move back to 'To Do' status for deferred tasks

**Chase/reminder prompt (follow-up nudges):**
- Made clearer that unassigning is a valid response when blocked/deferred
- Included the actual unassign command inline: `backlog task edit TASK-ID -a ''`
- Kept it concise to avoid prompt spam

### Result:

Agents now have clear, discoverable guidance that they can:
1. Unassign themselves if they can't do the task right now
2. Optionally move it back to 'To Do' so it goes back to the dispatch pool
3. This unblock pattern is shown in both initial and reminder prompts

All 59 tests pass.
<!-- SECTION:NOTES:END -->
