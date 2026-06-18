---
id: DECISION-1
title: SQLite append-only mailbox for agent comms
status: Approved
created_date: '2026-06-18 11:10'
labels: [architecture, comms]
---

## Context
When orchestrating multiple agent sessions (e.g. planner to executor), agents need a reliable bidirectional communication substrate (mailboxes). Senders need to push instructions, and recipients need to pull only unread messages. 

We need to avoid:
1. **Agent Context Bloat:** Agents shouldn't keep track of their own read cursors or history offsets, which wastes context tokens and prompt complexity.
2. **Write Contention:** Multiple agents writing to a single log file concurrently can lead to locking or inter-leaved line failures.
3. **Inode Exhaustion:** A pure directory-as-queue model (creating a separate file per message) will quickly exhaust system inodes when running large agent workflows.
4. **Reinventing the Database:** Designing seek offset tracking and custom parsers on top of a single flat log file is error-prone.

## Decision
We will implement the agent mailbox database using **SQLite** (configured with Write-Ahead Logging/WAL mode):
- A single `comms.db` file is created per `Thing` task-graph (e.g. under `things/<thing-id>/comms.db`).
- Senders append messages to a centralized `messages` table.
- A `subscription_cursors` table tracks the last-read message ID for each recipient.
- The subscription layer manages the cursor, allowing agents to simply pull new items via a clean CLI wrapper (e.g. `nudge comms pull --recipient <node-id>`).

## Schema
```sql
CREATE TABLE messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sender     TEXT NOT NULL,
    recipient  TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subscription_cursors (
    recipient    TEXT PRIMARY KEY,
    last_read_id INTEGER NOT NULL DEFAULT 0
);
```

## Consequences / Tradeoffs
- **Con: Database dependency.** Requires python/C to link/interact with SQLite (though python-sqlite3 is standard).
- **Pro: Diagnostic Side-channel.** Operators can open `sqlite3 comms.db` at any time to run queries, inspect the conversation history, or debug routing in real-time.
- **Pro: Replayability.** Because the `messages` table is append-only, conversation history is preserved. We can easily replay agent sessions step-by-step for debugging.
