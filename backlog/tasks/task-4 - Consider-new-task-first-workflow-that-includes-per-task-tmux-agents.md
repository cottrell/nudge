---
id: TASK-4
title: Consider new task first workflow that includes per-task tmux agents
status: To Do
assignee: []
created_date: '2026-05-12 07:08'
updated_date: '2026-05-12 07:14'
labels: []
dependencies: []
---## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Consider a different workflow ... task starts as a prompt, perhaps AI creates the task or the title whatever. Then from the existence of task and the working budget some simple thing starts a tmux agent and starts to work on that task via a simple prompt injection. This is almost a -p but would allow intervention and persistence in case it gets complex.

The question is how cleanup works. Who would do it etc. Persisting lots of agents is sort of ok but not ideal. One pattern in the wild is TASK_DONE token emission with a monitor that kills.
<!-- SECTION:DESCRIPTION:END -->
