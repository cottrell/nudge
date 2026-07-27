---
id: doc-4
title: Session supervisor process model
type: specification
created_date: '2026-07-27 12:16'
updated_date: '2026-07-27 12:41'
tags:
  - swarm
  - process-model
  - design
---
# Session supervisor process model

## Implemented model

- C `monitor-bin` remains the per-pane activity/status source.
- `session_worker.py` is the one long-running Python process per swarm session. It multiplexes durable-log/comms drains for every configured pane and writes the existing per-pane state files for status consumers.
- Babysit is an optional prompt group: `aiswarm babysit start|stop` changes each pane spec, which the same session worker reads on its next loop. It does not create or stop a separate per-pane process.
- Tasks is another group in that supervisor: `aiswarm tasks start|stop` writes/removes `tasks/enabled.json`; the worker calls `dispatch_once` on `poll_secs`. `aiswarm tasks once` remains a direct CLI pass.

## Process shape

A six-pane swarm has six cheap C monitor processes and one `session_worker.py` Python PID. Legacy per-pane worker PID files may point to that shared PID for status compatibility; they are not independent workers. There is no `tasks_dispatch.py` long-running process when tasks is enabled.

## Compatibility

`pane_worker.py` remains available for external one-pane invocations, but normal `aiswarm start` launches `session_worker.py`. `babysit.py` is no longer an entrypoint.

## Boundaries

The supervisor does not scrape terminal output or reimplement status detection. Durable-log protocol, task claim semantics, and per-swarm isolation stay unchanged.
