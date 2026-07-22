---
id: doc-3
title: 'Design: Peer Checkups on Stalled Assignments'
type: specification
created_date: '2026-07-22 21:15'
updated_date: '2026-07-22 21:15'
---
## 1. When to Trigger Peer Checkup vs. Chase

Currently, the nudge swarm has a **Chase** mechanism. A chase is a simple, lightweight nudge sent when:
- The assigned pane is **idle** (its monitor reports `idle`).
- The task is still open (reconcile hasn't cleared it).
- The chase interval (poll interval or custom `min_chase_secs`) has elapsed.

The chase is a reminder. It assumes the agent is healthy but just paused or forgot to output a state transition.

A **Peer Checkup** is an escalation workflow. It is triggered when the assigned pane is **stalled or unresponsive**. Instead of prompt-nudging the stuck agent (which is either unable to respond or trapped), we dispatch a checkup request to a **different, free pane** (a "peer" agent) to investigate and take action.

### Triggering Conditions (Chase vs. Peer Checkup)
1. **Target Pane Process Dead**: The shell command or the main process running inside the target tmux pane is no longer running.
2. **Monitor Process Dead**: The Unix socket of the monitor for the pane is dead/missing, or does not respond to a socket query.
3. **Working Stuck (Timeout)**: The pane has been in `working` state for longer than `BABYSIT_MAX_NONIDLE_SECS` (or `max_nonidle` in config, e.g., 30 minutes) without transitioning to `idle` or emitting new logs/activity.
4. **Rate Limited**: The pane's agent is rate limited (the babysitter reports `"rate_limited"` or the provider usage cache shows 0% remaining for that agent) and cannot make progress.
5. **Repeated Unresponsive Chases**: The pane has been chased $N$ times (e.g., 3 consecutive times) but has remained in a non-idle state (e.g. `unknown` or `working`) without completing the task or updating backlog state.

---

## 2. List of Usable Signals

To detect the above conditions, the task dispatcher and peer checkup logic can query several structured signals:

| Signal Name | Source | Meaning / Value | Usable for Peer Checkup Trigger |
| :--- | :--- | :--- | :--- |
| **Monitor State** | `query_monitor_state(session, pane)` | Unix socket query to `monitor.c`. Returns `idle`, `working`, or `unknown`. | Yes. If `unknown` or connection times out repeatedly, the monitor is unresponsive. |
| **Babysit State** | `babysit/<pane>.state.json` | Read JSON file. Contains keys like `last_state`, `last_action`, `last_nudge_at`, `ema` info. | Yes. Provides visibility into babysitter loop's observed state, including `rate_limited` when it's waiting on provider quota. |
| **Provider Quota** | `get_cached_provider_usage(agent)` | Queries `/tmp/nudge-usage-cache.json`. Returns remaining percent `pct`, resets, etc. | Yes. If remaining percent is 0% or very low, we know the agent on that pane is blocked by rate-limits/quota exhaustion. |
| **Pane Process ID (PID)** | Tmux query `#{pane_pid}` or `/proc/<pid>` | Checks if the shell or agent executable in the tmux pane is actually alive. | Yes. If the PID is dead, the agent has crashed. |
| **Chase Count** | `state.json` assignment | We can record `chase_count` inside `/tmp/nudge-swarm/<session>/tasks/state.json` under the pane's assignment. | Yes. If `chase_count >= 3`, we escalate to peer checkup. |
| **Time Claimed** | `claimed_at` | Timestamps of when the assignment was first made. | Yes. Can be used as a fallback watchdog timeout (e.g. task running for > 2 hours). |

---

## 3. Prototype Implementation & Non-Goals

### Prototype Workflow (How a checkup works)

When the task dispatcher runs `dispatch_once` and detects a stalled assignment (e.g., Task $T_1$ assigned to pane $P_1$ is stalled):
1. **Identify Peer**: Find a free task-enabled pane $P_2 \neq P_1$.
2. **Assign Checkup Task**: Instead of claiming a new task from the backlog, the dispatcher claims a special dynamic checkup task:
   - **Task ID**: `CHECKUP-P1` or `CHECKUP-T1`
   - **Title**: `Checkup on pane P1 (assigned to T1)`
   - **Description**: Contains a snapshot of the status of $P_1$ (PID status, monitor state, last logs/output tail from `monitor` socket, provider quota state, and $T_1$ backlog task details).
3. **Peer Agent's Instruction**: The dispatcher delivers a task prompt to $P_2$:
   ```
   A peer agent in pane P1 is stalled while working on task T1 (Title: <title>).
   
   Here is the diagnostic snapshot for P1:
   - Monitor State: <state>
   - Target PID: <pid> (Running: <yes/no>)
   - Quota: <quota remaining>
   - Last 5 lines of pane output:
     <tail output>
   
   Please investigate pane P1 and task T1.
   You can choose to:
   1. Unassign P1 from T1 so another pane can take it (use `backlog task edit T1 --status \"To Do\" -a \"\"`).
   2. Kill and restart the agent process in P1 if it's crashed or hung.
   3. Mark T1 as blocked / deferred if it cannot be completed now.
   4. Report your findings and actions to the user.
   ```
4. **State Transition**: Once $P_2$ takes action (e.g., unassigns $T_1$), the next dispatcher pass will reconcile the state, freeing up $T_1$ for other healthy panes.

### Non-Goals for Initial Version
* **Automatic Process Recovery (Auto-Restart)**: The dispatcher should *not* automatically kill and restart pane shells or agent processes. That requires user permissions and complex environment setups; instead, the peer agent or the user should make that decision.
* **Auto-Rescheduling without Checkup**: Simply unassigning the task automatically when a pane dies is a non-goal, because if the task itself is a \"poison pill\" (e.g., causing crashes or loops), auto-rescheduling it would lead to a cascade of crashes across the entire swarm. A peer agent checking it first acts as a safeguard.
* **Interactive Chat between Peer and Stalled Agent**: We do not attempt to send prompts directly to the stalled agent from the checkup agent.
