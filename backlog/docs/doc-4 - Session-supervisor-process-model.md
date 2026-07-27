---
id: doc-4
title: Session supervisor process model
type: specification
created_date: '2026-07-27 12:16'
updated_date: '2026-07-27 12:16'
tags:
  - swarm
  - process-model
  - design
---
# Session supervisor process model

## Current state

- C `monitor-bin` remains the per-pane activity/status source.
- `pane_worker.py` is currently one Python comms worker per pane; its babysit prompt group is optional.
- `tasks_dispatch.py` is a separate per-session Python polling process.

## Target state

One Python session supervisor per swarm multiplexes all pane comms drains, optional babysit prompt groups, and the task-dispatch polling group. The C monitors remain separate and are not reimplemented in Python.

`aiswarm babysit start|stop` continues to control only the prompt group. `aiswarm tasks start|stop` controls the dispatch group within the same supervisor. Per-swarm isolation remains; this is not a machine-global daemon.

## Migration

The rename to `pane_worker.py` is intentionally behavior-preserving. Supervisor consolidation is follow-on work: preserve the durable-log protocol, task claim semantics, per-pane runtime state, and explicit start/stop controls while replacing N per-pane Python processes plus the task dispatcher with one session process.
