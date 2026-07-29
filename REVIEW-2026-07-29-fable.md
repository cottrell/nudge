# nudge codebase review — Claude Fable 5 — 2026-07-29

Requested after a day of "stupid bugs and awful performance regressions." Full read of
`monitor.c`, `session_worker.py`, `pane_worker.py`, all of `swarm/`, `attach.sh`,
`tmux-send`, `Makefile`, plus empirical verification of the two worst suspects.
Baseline: `make build` clean, all 109 tests pass.

Backlog tasks filed: **TASK-53 … TASK-60**. Severity-ordered summary below, then
lower-confidence observations that did not become tasks.

## Verified bugs

### 1. monitor.c `log` query: out-of-bounds write past RESP_MAX (TASK-53, high)

`handle_query`'s `log` branch does `n += snprintf(out + n, cap - n, ...)` per line.
`snprintf` returns the *would-be* length, so with 50 buffered lines that each escape
large (control chars → `\u00XX`, 6 bytes each — exactly what ANSI-heavy agent TUIs
produce), `n` blows past `cap` (RESP_MAX = 56,320). After that, `out + n` points past
the static buffer and `cap - n` is negative → huge `size_t`, so subsequent snprintf
calls, `resp[rlen++] = '\n'`, and `write(conn, resp, rlen)` all operate out of bounds.

**Verified live**: fed 60 × 1000-control-char lines into `monitor-bin`, queried `log`,
got a **102,460-byte response from the 56,320-byte buffer**. The process survived
(silent BSS corruption), which is worse than a crash — `g_log`/state live in the same
segment. Reachable from the unix socket and the HTTP `/log` endpoint.

### 2. Status path shells out `bash -lc` + `nc` per pane per refresh (TASK-54, high)

`topology._query_monitor` / `socket_ready` run `bash -lc "printf 'status' | nc -U …"`.
Measured: **73.6 ms/query vs 0.1 ms** for a direct AF_UNIX socket (~700×). `-l` loads
the login profile every call. `aiswarm status -w` (default 1 s interval) with N panes
spends N×74 ms per refresh on subprocess churn; `start` pays it too via
`ensure_monitor`. The repo already contains two correct direct-socket implementations
(`tasksctl.query_monitor_state`, `pane_worker._query_socket`) — this is duplication
that never got consolidated. Likely a large chunk of the "awful performance" feel.

### 3. Task dispatch is O(N tasks) backlog subprocesses per pass (TASK-55, high)

Each `backlog` CLI call costs ~225 ms (measured). Per dispatch pass:

- `dispatch_once` fetches full detail (`backlog task <id> --json`) for **every**
  candidate just to read assignees — but `backlog task list --json` rows **already
  include `assignees`** (verified against this repo's backlog). Most detail fetches
  are avoidable.
- `view_assignment` bypasses the shared per-pass cache, and is called by *both*
  `reconcile_assignments` and `chase_assigned` → 2 extra subprocesses per assigned
  pane per pass, every pass, forever.
- `_claim_new_onto_free` calls `view_task_plain` (fresh fetch) immediately after
  `_task_or_none` cached the same task object.
- `tasksctl.status` dependency-gates **every** candidate (transitive closure, one
  subprocess per uncached dep) to render a 15-line preview — this is why
  `aiswarm tasks status` crawls on a busy backlog.

Compounding factor: dispatch runs inline in the `session_worker` loop, so a slow pass
blocks comms delivery and babysit nudges for **all** panes. Today's
"Eliminate repeated task recovery scans" commit (581b310) fixed one instance of this
family; the above are the surviving instances.

### 4. `babysit start --no-action` leaks dry-run into the supervisor (TASK-56, medium)

`cli.py` sets `BABYSIT_DRY_RUN=1` in its own env. If this invocation spawns the
session worker, the worker inherits it **for its whole lifetime** — a later plain
`babysit start` sees the pid alive, returns early, and every prompt/comms delivery
stays silently disabled until someone kills the worker. Conversely, if the worker was
already running, `--no-action` does nothing at all. Simulate mode must live in the
spec/runtime files the worker re-reads, not process env.

### 5. `broadcast --via-log` reports the wrong recipient set (TASK-57, medium)

The CLI prints per-agent-pane "log-broadcast to X", but delivery is per-pane
broadcast-cursor fan-out in `_drain_comms`, which runs for every comms-enabled pane
(shell/log panes included) and ignores `--include-nonmonitored`. Printed list ≠ actual
delivery, in both directions. Related: `aiswarm send` to a nonexistent pane queues an
event nobody will ever drain, silently.

### 6. `tasks.complete_statuses` is a phantom knob (TASK-58, medium)

`_complete_statuses` reads `cfg.tasks.complete_statuses`, but `TasksSpec` has no such
field and `_fill_tasks` never parses it — YAML setting it is silently ignored; the
dep gate always uses `{"done"}`. Meanwhile `view_assignment` hardcodes
`status == "done"` separately. Two "is complete" predicates, one of them fake.

## Smaller items (TASK-59, TASK-60, low)

- `session_worker` re-reads + json-parses every pane spec **every second** (and calls
  `babysit_runtime_paths` twice per pane) even though real work is throttled to 5 s.
  Gate on mtime like the existing config reload. (TASK-59)
- `stop_workers` / `tasks status` crash on an empty/garbage pid file (`int("")`).
- Babysit spec with only `short_prompt` never nudges: startup sends
  `long_prompt=""`, so `next_nudge_at` is never armed.
- `attach.sh` header comment documents `_0-0.sock` (dashes); code and Python both
  produce `_0.0.sock` (dots). Comment-only, but it's the kind of doc that eats an
  hour of debugging.
- `init.py` writes `start_directory: ./` into generated configs; `load_config` never
  reads it — dead key.
- `pane_worker` handles a `rate_limited` monitor state that `monitor.c` never emits.
- `process_running` returns False on `PermissionError` — wrong answer for a live
  process owned by another user on this shared machine.
- `resolve_backlog_dir`: explicit dir without `config.yml` passes; walk-up requires
  `config.yml`. Inconsistent validation.
- `validate_tasks_config` runs (and prints its babysit+tasks warning) every dispatch
  pass → log spam at poll frequency.

## Observations, not filed as tasks

- **monitor.c `json_str` truncation**: a 1023-char line can need ~6 KB escaped but
  `esc` is 2 KB — silent truncation mid-escape can emit a dangling `\` before the
  closing quote in pathological cases; worth an eye when fixing TASK-53.
- **Signal handler** calls `fclose` (not async-signal-safe). Practically harmless here.
- **`tick_thread`** wakes 10×/s per pane to check the idle deadline. Negligible on
  this machine, but it is 10 wakeups/s × panes of pure polling; a computed sleep
  would be free.
- **EMA pacing** (`_next_wait`): `max(reset_ts - now, 3600)` *inflates* the horizon
  when reset is <1 h away, lengthening waits near reset. If intentional
  (conservatism near reset), a comment would save the next reader; a `min` there
  would be the opposite policy.
- **Quota cache** (`/tmp/nudge-usage-cache.json`): read-modify-write of the whole
  file from multiple processes/threads; `os.replace` prevents corruption but
  concurrent agents can drop each other's entries. Self-healing (TTL), so low value.
- **`get_swarm_agent-monitor_report`** runs the agent-monitor CLI twice per agent serially
  (today + week, 15 s timeout each). `av-usage -w` repeats the full set every cycle.
  Fine as a human command; don't ever put it in a worker loop.
- **Architecture**: the consolidation to one `session_worker` per swarm (TASK-48
  line of work) is sound and the recent regression tests around `stop_workers` /
  PaneSpec are exactly the right lock-in. The remaining structural risk is that the
  single loop now serializes *everything* — comms, babysit, dispatch, healthchecks —
  so any newly added blocking call (subprocess, network) degrades all panes at once.
  Cheap guard: log a warning when one loop iteration exceeds, say, 2× poll budget.
- **Grok special-casing in monitor.c** (title-based state, exempt from idle timeout)
  is the one agent-specific pattern in an otherwise content-agnostic design; it's
  flagged in CLAUDE.md as intentional, but the `ingest` early-return structure around
  it is easy to break — a fixture-driven test per branch would lock it.

## What I'd do first

1. TASK-53 (memory corruption, small fix, add regression test).
2. TASK-54 (one shared socket helper; biggest UX win per line changed).
3. TASK-55 (list-row assignees + cache in `view_assignment`; biggest dispatcher win).
4. TASK-56 (silent no-delivery trap).
