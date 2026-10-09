---
id: TASK-87
title: >-
  Explore 'human-in-the-loop / human is in' presence state and agent autonomy
  guidance
status: To Do
assignee: []
created_date: '2026-10-09 08:57'
updated_date: '2026-10-09 10:39'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agents frequently block waiting for human approval overnight or while the user is away (e.g. asking 'sound good?'), stalling unattended progress. A mechanism is needed to signal whether a human is currently available/in-office, or to time out and default to autonomous action or non-blocking handoff.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Define presence semantics (global vs per-swarm state, e.g. 'aiswarm human in/out' or file/flag in runtime/config)
- [ ] #2 Evaluate passive timeout vs explicit toggles vs auto-detection (e.g. prompt timeout or idle terminal detection)
- [ ] #3 Provide guidance and naming conventions for AGENTS.md so agents know when and how to proceed autonomously
- [ ] #4 Document concrete design recommendations or CLI commands in nudge/aiswarm
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Notes and discussion points (no decisions finalized):

1. Dual Nature of Agent Behavior:
- When a human IS present: Agents SHOULD ask questions, seek clarification, value human time, and not make the human wait unnecessarily.
- When human is AWAY: Agents should not block/wait for approvals. They should proceed with safe, best-judgment execution, recording assumptions and committing progress.
- Crucially: this is not about blindly nudging all idle prompts. It is about informing agents of human availability so agents calibrate their behavior and interaction style accordingly.

2. Interaction with Subscription / Quota Model:
- Complex interplay with model subscriptions: goal is often to maximally burn remaining quota/subscriptions towards the end of each billing/reset period, but not exhaust them prematurely (unless explicitly pushed).
- Quota is noisy, opaque, and hard to observe directly. Agent pacing and autonomy needs to be sensitive to both human availability and quota budget posture.

3. Scoping & Presence Architecture:
- Official state should be per-swarm (e.g. in swarm config or runtime), but with a default of None / use_global so users don't have to configure each swarm independently.
- Global presence marker: Standalone utility/market or system-level indicator for human presence.

4. Passive Presence Detection Investigation:
- Need to investigate what is practically possible to observe passively on the host/session (e.g. tmux client activity timestamps, window focus, input idle times across TTYs/X/Wayland/SSH) vs manual or lease-based overrides.

5. Passive Detection via Tmux Clients:
- Always running inside/via tmux (et -> tmux, or desktop terminal -> tmux).
- tmux client activity (`tmux list-clients -F "#{client_activity}"`) provides the exact timestamp of last human input received by tmux, completely immune to agent output noise.
- Idle time is simply `min(now - activity)` across attached clients.
- Enables a pure on-demand / zero-daemon model: presence state can be evaluated instantaneously on query by combining explicit manual override (in/out/lease) with passive client idle threshold fallback.

6. Key technical property confirmed:
- `tmux send-keys` / message injection targets panes, NOT client TTYs.
- `#{client_activity}` tracks strictly client input (human keyboard/terminal events entering tmux via the attached tty/socket).
- Therefore, automated `aiswarm send` / script injections will never trigger or reset `#{client_activity}`.

7. Query Cost & Storage Analysis:
- `tmux list-clients -F "#{client_session} #{client_activity}"` executes in ~3ms and queries the tmux server directly in a single call across ALL attached clients and sessions. No looping over sessions required.
- However, if a client is detached, tmux drops it from list-clients.
- Storage recommendation:
  - Ephemeral / live state in `/tmp/nudge-swarm/presence.json` (or `/tmp/nudge-presence.json`), matching `runtime.json` convention.
  - User configuration (default idle threshold e.g. 900s, manual override if made persistent) in `~/.config/aiswarm/presence.yaml` or swarm config.
  - Per-swarm presence: derived lazily or recorded in `/tmp/nudge-swarm/<swarm>/presence.json` (or merged into `runtime.json`).
  - Global presence: max timestamp across all attached clients, or fallback to latest recorded activity in `/tmp/nudge-swarm/*/`.

8. Client vs Session Nuance:
- `tmux list-clients` iterates attached terminal connections (clients), not sessions directly.
- Each client is currently viewing/controlling a specific session (`#{client_session}`).
- Multiple clients can be attached to one session, or multiple sessions can be attached by separate clients (e.g. separate terminal windows or tabs).
- Detaching: When a human disconnects, the client vanishes from `list-clients`, but the persistent state cache in `/tmp` preserves the timestamp of when they were last seen active before disconnect.

9. Pure Stateless / On-Demand Architecture:
- Passive detection requires ZERO persisted state files: whenever queried, `tmux list-clients -F "#{client_session} #{client_activity}"` is invoked directly (~3ms).
- If no clients are attached to tmux: passively OUT immediately.
- If clients are attached: calculate `idle = now - max(activity)`. Compare against idle threshold (e.g. 15m).
- Only manual overrides require state storage:
  - Global override: e.g. `/tmp/nudge-swarm/presence_override.json` (or `~/.config/aiswarm/presence_override.json`).
  - Per-swarm override: in the swarm runtime dir `/tmp/nudge-swarm/<swarm>/presence_override.json` or config.
  - Can optionally store an expiry/lease timestamp (`until`) so overrides cleanly auto-expire.
- Pure on-demand, no background daemon, zero synchronization bugs or stale cache issues.

10. State Model and Naming Exploration:
- Hierarchy: Swarm-local override -> Global override -> Auto (passive tmux).
- Local modes:
  - Default: `inherit` / `use_global` (follows whatever global evaluates to)
  - `in` / `out` (explicit local pin, ignoring global)
  - `auto` / `local_auto` (uses passive tmux activity specifically on clients attached to THIS swarm session, ignoring global)
- Global modes:
  - `auto` (default: checks passive tmux across ANY attached client)
  - `in` / `out` (explicit global pin)
- Config:
  - Idle threshold (default e.g. 15m / 900s), configurable in config.yaml or cli flag.

11. Advice from Claude in pane 0.2:
- Scope in the command/noun, so mode words stay symmetric and clean:
  - Local modes: `global` (follow global, replaces inherit; names the source of truth without implying a tree/hierarchy), `in`, `out`, `auto` (passive detection, only clients attached to this swarm).
  - Global modes: `auto` (passive across all clients), `in`, `out`.
  - Avoid `active` (collides with monitor vocabulary: working/idle).
  - CLI command structure:
    `aiswarm presence global in|out|auto`
    `aiswarm presence local in|out|auto|global`
  - Status display: print effective state alongside origin:
    e.g. `local: auto (this swarm)`, `global: auto (3 clients, idle 4m)`, `effective: in`.
<!-- SECTION:NOTES:END -->
