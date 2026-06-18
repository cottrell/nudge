# Grok Notes on Nudge/Alt Architecture (2026-06-13)

## LangGraph Clarification
LangGraph is **primarily an orchestration / workflow framework**, not a replacement for the individual agent harnesses (Claude Code, Codex CLI, Gemini, Grok Build, Aider, etc.).

- It lets you declare "Things" as **graphs** (nodes + edges, conditional routing, parallel, cycles, supervisor patterns).
- Built-in **persistence/checkpointing** (thread IDs, Sqlite/Postgres savers) — exactly the durable DAG record + session revival you want.
- State is passed between nodes; nodes can be LLM calls, tools, or calls to other agents.
- Excellent for the *meta* layer: persistent Thing DAG, supervisor/pulse logic, revival decisions, audit.
- **Not** the harness: the actual model interactions still go through LangChain (or direct) to providers. You still launch real CLI sessions or use APIs inside nodes.

You can steal the concepts (graph as Thing, checkpoint = persistent record with session_refs, supervisor node = pulse) without adopting the full Python framework if you want to stay lightweight and harness-agnostic.

Strongest existing pattern match for your "persistent record of the DAG + session ids so parent can revive child or start new" goal.

## Overall Assessment
Your direction is sane and a clear improvement.

It solves:
- Fragile tmux scraping + constant per-pane nudging.
- Quadratic rate-limit burn from unbounded long-lived sessions (by scoping Things + explicit revival instead of manual /clear).
- Need for resumability across restarts/machine changes.
- Independence (no single harness owns the swarm).

Bifrost as mostly transparent routing + quota oracle fits perfectly. The pulse will be the main consumer ("does this role/client have headroom?"). Individual harnesses can optionally route through it for model selection/caching, but don't have to.

Backlog tasks remain the human-visible DAG nodes. Good.

Embracing concurrent work on one shared tree ("factory floor") is viable if the persistent record + mailboxes provide enough coordination signals.

## Recommended Minimal-Invention Approach

Core principle: **Keep the persistent record + pulse as the thin, portable orchestration layer outside any harness.** Each harness instance (Claude pane, Grok headless, etc.) is a "node" that lives mostly independently and communicates via the shared substrate.

### Persistent Record (the durable DAG + revival source of truth)
Location: `alt/state/things/<thing-id>/` (git-friendly, alongside backlog).

Minimal files:
- `graph.json` — the DAG structure + live session refs + revival history.
- `mailbox/` or per-node logs for bidirectional comms.
- Optional `checkpoints/<node-id>.json` for richer state snapshots.

Example `graph.json` sketch:

```json
{
  "thing_id": "thing-20260613-foo-refactor",
  "goal": "Refactor auth module per task-42",
  "root_backlog_task": "task-42",
  "status": "active",
  "created_at": "2026-06-13T...",
  "nodes": {
    "planner-1": {
      "role": "planner",
      "harness": "claude",
      "session_ref": "tmux:nudge:0.1",   // or "headless:uuid-123" or "grok-session-abc"
      "status": "done",
      "last_active": "...",
      "mailbox": "things/thing-.../planner-1.log",
      "parent": null,
      "children": ["impl-2", "review-3"],
      "revival_history": []
    },
    "impl-2": {
      "role": "implementer",
      "harness": "grok-build",
      "session_ref": "headless:uuid-456",
      "status": "working",
      "last_active": "...",
      "mailbox": "things/.../impl-2.log",
      "parent": "planner-1",
      "children": [],
      "revival_history": ["revived 2026-06-12 from old-ref-789"]
    }
  },
  "edges": [["planner-1", "impl-2"], ...],
  "last_pulse": "..."
}
```

The record is the thing the pulse reads/writes. Backlog tasks are the "published" view of important nodes (status, notes, subtasks).

This gives revival: parent/pulse looks at `session_ref`, decides "still alive? send targeted continue message" vs "dead or wrong quota profile — spawn fresh and update ref".

### Top-Level Pulse / Nudge (the metaswarm supervisor)
Lightweight external loop (Python script, small daemon, or even a scheduled headless Grok process — keep it swappable).

Responsibilities:
- Wake periodically or on events (inotify on backlog/alt/state).
- For ready tasks / idle nodes:
  - Query Bifrost for quota headroom (per role or client_id mapping).
  - Consult graph.json + backlog.
  - Action: 
    - Nudge existing living child (write to its mailbox + send short "new mail / continue" via its session_ref transport).
    - Revive: if session_ref points to something resumable, use it + fresh context from record/mailbox.
    - Spawn new: launch the chosen harness (tmux new pane with command, or `grok -p "..." --session-id ...` headless, or claude/codex equivalent) with initial prompt that includes Thing ID + mailbox location + "maintain channel until parent declares done".
  - Update graph.json with new ref / status.
- Cleanup: when a node reaches terminal state, optionally kill the session_ref (if controllable) or just leave it.

This replaces the old distributed babysit + manual clears. The pulse owns "if idle and quota left".

Use your existing `alt/scripts/dispatch.sh` style for launch, extended with record updates.

### Living Bidirectional Children + Comms Substrate

**Backlog vs Mailboxes (important distinction)**

- **Backlog** (the CLI tool + tasks/): High-level, structured, human-visible, auditable coordination. Use for tasks, subtasks, status, notes, ACs, final summaries, dependencies. This is your "published" DAG view. Great for overview and cross-Thing references. Agents read with `backlog task X --plain` and edit via CLI commands. **Not** the general low-latency message bus.

- **Mailboxes / directed logs**: Lightweight, append-only files for direct parent <-> child (or any directed pair) messaging. This is the "live-ish prompt injection" replacement for raw tmux-send when you want durability and harness independence.

**Directed pair logs (yes, exactly as you described)**

Recommended convention:

```
things/<thing-id>/comms/
  parent-foo__child-bar.log     # from parent to this specific child
  child-bar__parent-foo.log     # from child back to parent
  child-bar__review-3.log       # sibling or cross-child if needed
```

Or flatter per-node:
- `things/<thing-id>/<node-id>-inbox.log` (everything addressed to this node)
- Or explicit directed files as above.

Simple format inside the log (human + machine readable):

```
[timestamp] [from:planner-1] Continue with the error handling refactor. See new requirements in backlog task-42.
[timestamp] [from:impl-2] Implemented basic retry. Tests in tests/auth_retry_test.py. Question: should we also update the config schema?
```

**Consumption ("how does the child see it?")**

Every child prompt includes something like:

"You are node 'impl-2' in Thing 'thing-20260613-foo-refactor'.
- Use `backlog` CLI for high-level task state.
- Check your incoming mailboxes at the start of work and after significant steps:
  - `cat things/thing-20260613-foo-refactor/comms/*__impl-2.log` (or your specific inbox).
- Post updates, questions, findings, and status back into the appropriate outgoing log.
- Stay responsive to parent direction until the parent marks the sub-job complete in the backlog/graph."

The pulse (or parent) can also write a short poke + the real content into the log.

**Live-ish sending of prompts (the tmux-send part)**

You are correct — pure log writing is "fire and hope the child reads eventually."

The "live-ish" piece is the **poke/transport** layered on top of the durable log:

1. Write the actual prompt/message to the directed log file (durable, survives restarts, works for headless or non-tmux agents, harness-agnostic).
2. Send a short wake-up via the live transport for that session_ref:
   - For tmux panes: `tmux-send <target> "New message from parent in your inbox for this Thing. Read the latest in comms/parent-foo__child-bar.log and continue."`
   - For headless/Grok/etc.: equivalent (perhaps `echo "check inbox" >> some-control-pipe`, or just rely on the child being in a loop that polls, or use the harness's native resume mechanism if it has one).
   - The short poke is just to make the agent "notice" soon. The real payload lives in the log.

This is basically what you were already doing with tmux-send, but now the important content is in durable, versioned, grep-able files instead of relying on the pane's scrollback never being cleared.

**Any directed pair log?**

Yes — the graph.json already has the edges, so you can allow comms along edges by default (parent-child bidirectional). For cross-Thing or grandparent-grandchild you can either:
- Explicitly create extra directed logs, or
- Fall back to backlog (create a cross-reference task or append notes).

Scoped by default to the Thing's tree keeps noise down.

**Is there a better live push across arbitrary harnesses?**

For black-box CLI agents (full UIs in tmux or their own processes), reliable "push a prompt and get it processed immediately without the agent polling" is hard without harness-specific hooks (Claude's session JSON, direct stdin to a headless process, etc.).

The durable log + poke (tmux-send or equivalent) + prompt discipline to check inbox is the pragmatic, low-invention way that works across Claude, Codex, Grok, Gemini, etc.

If you later add a small MCP or socket bus that all harnesses can talk to, you could make the poke more uniform, but the log files remain the durable source of truth.

### Gateway Role (optional)
Use LiteLLM (lighter for custom/ sub-friendly proxying) or Bifrost only when you have real keys or want extra caching/routing.

- Pulse can query for quotas/headroom.
- Route selectively (planners to APIs via gateway; workers stay on direct sub CLIs or local).
- Not required for the core Thing + subscription harness flow.

### How Grok Build Fits (as one participant)
- Can be just another harness node (like "grok-build" in the graph.json example above).
- Its strengths for this world:
  - Native subagents + `resume_from` + worktree isolation + personas = good internal hierarchy inside one Grok node (a "foreman" that manages its own sub-DAG without polluting the global record).
  - `graphify` skill: turn a high-level goal + backlog context into a concrete task DAG that seeds the graph.json.
  - `plan` mode + design/implement skills: strong for planner/implementer roles with built-in review loops and artifact handoff (maps cleanly to mailbox + record updates).
  - Scheduler + background tasks + `monitor` tool: could implement the pulse itself (if you run a Grok instance in that role).
  - `todo_write`: shared blackboard inside a Grok node or across if passed via files.
- Important: the persistent record + pulse stay the portable layer. Grok is not required to be the center. You can use it for complex nodes or the orchestrator when it makes sense, then swap.

When running Grok here, I can help maintain these notes, graphify the current backlog + alt/ to seed a graph.json, or prototype the pulse/record logic.

### Minimal Next Steps (low invention)
1. Define the `graph.json` schema + mailbox convention in a small doc (start with the sketch above).
2. Extend `dispatch.sh` (or new `launch_thing_node.sh`) to accept thing-id + node-id + record path, launch the harness, and update the record on spawn.
3. Tiny pulse loop (Python or shell) that:
   - Reads graph.json + backlog.
   - Hits Bifrost (simple HTTP or whatever its interface) for quota.
   - For ready nodes: decide revive/spawn/nudge, call the launcher, update record.
4. Update child prompts (in `prompts/`) to reference Thing/node + mailbox + backlog discipline.
5. Use `graphify` (the skill) on your backlog/tasks + alt/ docs to bootstrap an initial graph.json for a real project.

This stays close to what you already have in alt/ (session_id handling, state dir, ClawTeam graph ideas, dispatch) and backlog (tasks as DAG).

### Open Questions to Resolve
- Exact quota query interface from Bifrost (client_id per role?).
- How to "address" a live session_ref for nudges across harnesses (tmux-send for panes, direct stdin for headless, etc.).
- Cleanup policy for finished living children.
- How deep the persistent record needs to go (full state per node or just session_ref + summary?).

This approach lets you stop fighting the harnesses' long-session behavior and instead treat them as somewhat disposable, addressable workers coordinated by the record + pulse.

---

*These notes written from inside a Grok Build session in the nudge context. Goal: help without assuming Grok owns the swarm.*

## Comms / Mailboxes Clarification (added 2026-06-13 follow-up)

User asked: "ok mailboxes is fine I guess, you mean backlog? I was using a tmux send type thing. But I can't remember if there was a solution for more of a kind of live-ish way of sending prompts? It feels like writing to logs/mailboxes could work I suppose. Perhaps there is no other way really. We probably have like parent_x -> child_y log? and we consume from that somehow? and we can have any directed pair log? I really was hoping this kind of project already existed in the wild."

**Distinction**
- Backlog = structured task board (tasks, subtasks, notes, status, ACs). Visible, auditable, CLI-driven. Use for the high-level DAG nodes and human coordination.
- Mailboxes / directed logs = the general-purpose, low-ceremony message channel between specific pairs of nodes. This is what replaces "just tmux-send a full prompt" for durability and cross-harness use.

**Directed pair logs — yes**
Exactly as you said:

`things/<thing-id>/comms/parent_planner-1__child_impl-2.log`
`things/<thing-id>/comms/child_impl-2__parent_planner-1.log`

(Or a per-node inbox that aggregates everything addressed to it.)

Anyone (parent, child, the pulse, even a grandparent via explicit allowance) can append to the appropriate directed file.

**Live-ish sending**
The durable log write is the payload.

The "live" part is a short wake-up poke using whatever transport makes sense for that session_ref:
- tmux panes → `tmux-send <target> "New parent message in your comms inbox. Read the latest lines in parent_planner-1__child_impl-2.log and continue."`
- Headless processes → equivalent poke (stdin to the process if you control it, or a control file the child watches, or just let the child's natural loop pick it up).
- The poke can be tiny. The real prompt lives in the log so the child can read the full context even if it was restarted or the pane was cleared.

This is the pragmatic combination that works when the "agents" are full black-box CLI harnesses rather than functions inside one runtime.

**Consumption**
In the prompt for every node:
"Periodically (especially at the beginning of work or when the parent pokes you) read your incoming directed logs under things/<thing-id>/comms/*__<your-node>.log. Treat new entries as additional instructions or context from the named sender."

No perfect universal "push a prompt into an arbitrary running CLI agent session and have it processed instantly without the agent cooperating" exists across all the harnesses you want to use. The log + poke + prompt discipline is the standard pattern in this space (shared memory/files + external wake-up).

**Existing projects in the wild**
Closest things use internal shared state inside one framework (LangGraph passes messages via its graph state / channels between nodes; Swarms / AutoGen have message buses between agents they control).

Nothing is a perfect off-the-shelf for "orchestrate a bunch of independent, long-lived, vendor CLI agent sessions (Claude in tmux, Codex, Grok headless, etc.) with persistent DAG, revival, living bidirectional comms on a single shared git tree, driven by a thin pulse that only cares about backlog + Bifrost quotas."

Your setup (black-box harnesses + tmux/headless mix + shared tree "factory" + minimal deps) is somewhat unique, which is why you're having to assemble the pieces. The good news is the pieces (backlog for tasks, files for durable directed comms, a small pulse script, Bifrost for quotas, graph.json for the revival record) are all very small and leverage what you already have.

If a project like "orchestrator for multiple existing agent CLIs with file-based actor mailboxes + DAG checkpointing" existed cleanly, it would be worth adopting. Closest inspirational codebases are the internal comms layers in LangGraph or ccswarm-style setups, but they usually assume more control over the agents.

**Recommendation**
Go with the directed pair (or per-node inbox) logs + the short poke via tmux-send (or harness equivalent). It's simple, debuggable (just cat the log), survives everything, and works for any directed pair (parent-child, siblings, cross-Thing if you allow it).

We can prototype a tiny `send_comms.py` or shell helper that takes (thing-id, from-node, to-node, message) → appends to the right log file + does the appropriate poke based on the session_ref in graph.json.

This keeps the "each agent has its own thing" while giving controllable, persistent, bidirectional channels.