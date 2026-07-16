---
id: doc-2
title: 'Agent-to-agent handoff via send, backlog, and ping'
type: guide
created_date: '2026-07-16 09:24'
updated_date: '2026-07-16 09:24'
---
# Agent-to-agent handoff (send + backlog + ping)

## Problem

Agent A wants agent B to do work. The bad default is:

- A attaches to B's tmux pane, or keeps re-capturing B's scrollback
- A sits in a "streaming spectator" loop, burning tokens and doing nothing useful
- The only durable record is whatever happened to be on screen

**Prefer:** short durable pokes over the comms log, long-form work product in backlog, and a short completion ping back. Neither agent needs to watch the other's pane.

## Roles of each channel

| Channel | Role | What goes there |
|---|---|---|
| `aiswarm send` (comms log) | **Poke / wake** | Short instruction, task id, "done" ping |
| Backlog task | **Work product + status** | Goal, AC, notes, final summary, Done |
| Pane attach / capture | **Debug only** | Operator debugging, not agent coordination |

Delivery rules already enforced by the swarm:

- `aiswarm send` appends to the session SQLite log (`/tmp/nudge-swarm/<session>/comms.db`)
- The per-pane **comms worker** delivers via `tmux-send` when the recipient pane is **idle**
- Sender does **not** wait for delivery; return is just an event id

## Example workflow (peer A → peer B)

Assume swarm config `./swarm/nudge.yaml`, session name from that YAML, panes:

- `0.0` = agent A (requester)
- `0.1` = agent B (worker)

### 1. A creates (or reuses) a backlog task for the work unit

```bash
backlog task create "Review PR plumbing in swarm/cli.py" \
  --ac "List risks for send path" \
  --ac "Note any missing tests" \
  -a "pane:0.1" \
  --plain
# → TASK-NN
```

Optional: put reply-to metadata in the description or notes so B knows who to ping:

```text
Reply-to pane: 0.0
On complete: set Done, write final-summary, then aiswarm send cfg 0.0 "TASK-NN done"
```

### 2. A pokes B via durable log (do not attach)

```bash
CFG=./swarm/nudge.yaml

aiswarm send "$CFG" 0.1 "$(cat <<'MSG'
Please take TASK-NN.

1. backlog task TASK-NN --plain
2. Do the work; append notes as you go.
3. When done: backlog task edit TASK-NN -s Done --final-summary "..."
   (or: backlog task complete TASK-NN after status Done)
4. Ping me (do not stream your pane at me):
   aiswarm send ./swarm/nudge.yaml 0.0 "TASK-NN done — read backlog task TASK-NN for results"
MSG
)"
```

A then **continues its own work** (or idles). A does not `tmux attach`, does not `capture-pane` in a loop, and does not wait on B's scrollback.

### 3. B works from backlog, not from chat history

When idle, B's comms worker injects the poke. B:

```bash
backlog task TASK-NN --plain
# ... implement / review ...
backlog task edit TASK-NN --append-notes "Risk: X. Missing test: Y."
backlog task edit TASK-NN -s Done --final-summary "Reviewed send path; risks and missing tests in notes."
```

If B needs clarification, write it on the **task** (comment/notes) and poke A with a short send — still no pane streaming.

### 4. B pings A when done

```bash
aiswarm send ./swarm/nudge.yaml 0.0 "TASK-NN done — results in backlog (final-summary + notes). Not waiting on your pane."
```

### 5. A consumes the result from backlog

When A is idle, the completion ping is delivered. A:

```bash
backlog task TASK-NN --plain
# use final-summary / notes as the reply body
```

A never needed B's live stream.

## Message templates (keep them short)

**Request poke (A → B):**

```text
TASK-NN for you. Read: backlog task TASK-NN --plain
Reply channel: backlog notes/final-summary on TASK-NN
When done ping: aiswarm send <cfg> <my-pane> "TASK-NN done"
```

**Done ping (B → A):**

```text
TASK-NN done. See backlog task TASK-NN (final-summary).
```

**Blocker ping (B → A):**

```text
TASK-NN blocked: need decision on X. Question in backlog task comment.
```

Do **not** put large diffs, full file contents, or long reasoning in `aiswarm send`. That expands into the recipient's context via tmux-send and fights babysit `/clear` discipline. Put bulk content in git commits + backlog notes.

## Anti-patterns

1. **Spectator attach** — A watches B's pane until idle. Wastes A, loses durability across clears.
2. **Giant send payloads** — treat send as SMS, not email with attachments.
3. **Status only in chat** — if B is `/clear`ed or restarted, chat is gone; backlog survives.
4. **Busy-wait polling** — A looping `aiswarm log --pending` or capture every few seconds. Prefer: do other work; the done-ping is the wake signal. Optional light poll of `backlog task TASK-NN --plain` if no ping after a long time.
5. **Raw `tmux send-keys`** — use `aiswarm send` or `./tmux-send`; raw send-keys is unreliable for Enter.

## How this relates to `aiswarm tasks`

| Pattern | Who assigns work | Best for |
|---|---|---|
| **Peer handoff (this doc)** | Agent A creates task + `send` to B | Ad-hoc review, help request, cross-pane question |
| **`aiswarm tasks` dispatcher** | Session dispatcher claims `To Do` tasks onto free `nudge.tasks.enabled` panes | Pull-based backlog drain when panes are free |

They compose:

- Dispatcher can land TASK-NN on B without A existing.
- A can still create TASK-NN and poke B if B is a specific specialist pane.
- In both cases, **completion is backlog status Done**, not "pane went idle".

## Operator checklist

```bash
# identity / targets
cat /tmp/nudge-swarm/<session>/self-awareness.txt
cat /tmp/nudge-swarm/<session>/runtime.json | head

# send / inspect
aiswarm send ./swarm/<project>.yaml 0.1 "short poke"
aiswarm log ./swarm/<project>.yaml --pending
aiswarm log ./swarm/<project>.yaml --pane 0.1
aiswarm cursors ./swarm/<project>.yaml

# backlog
backlog task list --plain
backlog task TASK-NN --plain
```

## Acceptance of this pattern

A handoff is "done correctly" when:

1. Work request exists as a backlog task with clear AC / reply instructions.
2. Worker was woken with a short `aiswarm send` (or tasks dispatch), not by A attaching.
3. Results live in backlog (notes + final-summary + Done).
4. Requester was woken with a short done-ping `aiswarm send`.
5. Neither agent depended on the other's live tmux stream for the reply.
