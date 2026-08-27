---
id: doc-5
title: 'Voice, subscription and agent communications research'
type: other
created_date: '2026-08-27 10:42'
updated_date: '2026-08-27 10:43'
tags:
  - voice
  - architecture
  - mcp
  - subscriptions
  - comms
---
# Voice, subscription and agent communications research

## Goal

Enable a user walking with a phone to submit notes or work to desktop swarms and later explicitly pull correlated replies into a voice conversation. The user does not want unsolicited notifications or automatic speech.

Desired flow:

```text
phone voice conversation -> submit -> durable conversational mailbox -> nudge swarm
phone voice conversation <- explicit reply retrieval <- correlated agent result
```

## Non-negotiable subscription boundary

The only subscription capability treated as durable is the provider allowing the user to log in and run its official CLI. Nudge may operate that CLI as an interactive black box.

Do not make these required architecture:

- subscription OAuth exposed to third parties;
- reusable provider tokens;
- API-compatible subscription endpoints;
- embedded third-party runtimes;
- connector entitlements;
- claims that OAuth and native application usage share quota or billing.

All such paths are experiments even when currently functional. An auth audit must identify the exact executable or surface, credential source, entitlement and quota bucket, provider support status, fallbacks, and evidence that no API key or PAYG endpoint was used.

Observed local evidence overrides stale product documentation: both Grok and GPT voice have working connector connectivity to `local-mcp` in this setup. Future research must test the actual configured surfaces rather than infer capability solely from public help text.

## Current local architecture

`local-mcp` is a small authenticated Cloudflare-tunnelled ingress with tools to create Backlog tasks and send nudge messages. Nudge runs official provider CLIs in tmux, uses content-agnostic activity monitoring, a SQLite durable event log and per-recipient cursors, and delivers messages when panes become quiet.

This preserves subscription economics because expensive work remains in official interactive applications and CLIs. The connector transports small structured messages rather than converting a subscription into an API.

## Conversational mailbox model

MCP is an adapter, not the mailbox. A minimal provider-neutral envelope likely needs:

- message ID and conversation ID;
- sender and recipient;
- reply-to/correlation;
- payload and timestamps;
- queued, delivered, acknowledged, completed or failed state.

Likely operations are submit, list conversations, read replies after a cursor, acknowledge, and continue a conversation. Backlog holds durable work intent and results; short mailbox events wake or correlate participants.

Nudge already has an approved SQLite mailbox decision and an implementation using `events` plus `cursors`. Avoid growing this into general email without demonstrated need.

## Existing messaging systems

### MCP Agent Mail

Closest semantic match: identities, inboxes, searchable threads, acknowledgements, attachments and optional file reservations over MCP, backed by SQLite and Git. It is a credible candidate for an optional backend or source of envelope semantics. It is also substantially broader than nudge comms and does not replace nudge's quiet-time pane delivery.

### Redis Streams / NATS JetStream

Provide durable logs, consumer tracking and acknowledgement, but introduce a broker process and still require application-level identities, threads, task correlation and tmux wake routing. They are unjustified at current single-machine scale unless cross-process throughput or independent consumers materially outgrow SQLite.

### MQTT

Good device pub/sub, but retained messages and QoS are not a conversational mailbox or durable threaded history.

### Email / Matrix

Mature messaging semantics but high operational and protocol surface for local agent IPC. Reconsider only if standard clients, federation or multi-machine human messaging become primary requirements.

### Current recommendation

Keep SQLite for now. Define a small stable envelope and adapters. Compare compatibility with MCP Agent Mail before adding advanced mailbox features. Keep wake/delivery policy in nudge, separate from storage.

## Phone and voice surfaces

### Native Grok/GPT voice plus connector

Preferred first path because it is already working and stays on official subscription surfaces. Add conversational inbox operations to `local-mcp`, then test submission, ending the session, starting a later session, retrieving the correlated result, and continuing discussion.

### OpenClaw as a separate northbound gateway

Potentially useful for mobile Talk, persistent conversational context, semantic routing and multiple channels. It should sit above nudge, not replace swarm execution:

```text
OpenClaw phone/Talk -> restricted nudge adapter -> mailbox -> swarms
```

OpenClaw subscription OAuth is not durable under the project rule. A trial must not rely on it. If OpenClaw cannot act only as a phone/router while delegating expensive reasoning to official CLI processes, it is a poor fit. Restrict any trial to submit/list/read/continue operations with no shell, filesystem or repository access.

### Open WebUI / LibreChat

Useful polished browser voice interfaces. Browser STT/TTS or local Whisper/Piper can avoid speech API charges, and MCP can expose nudge tools. However, tool selection normally requires a model served through an API or local endpoint. Using a provider API violates the subscription objective; building a custom official-CLI bridge recreates the hard part. A local model might be adequate only for narrow routing and needs reliability testing.

### Telegram bot relay

Strong low-complexity alternative phone interface. Phone dictation supplies text; voice notes can be transcribed locally; Telegram supplies conversation history and audio playback. A deterministic convention such as `nudge <project>: <message>` can route without another model. For natural references, the bot can keep `chat -> last project/conversation` mappings or delegate interpretation to an official CLI router pane.

The bot must not push completion notifications. It stores results and answers only an explicit `/check`, `check replies`, or continuation request. Telegram then becomes a separate conversation surface rather than injecting replies into native Grok/GPT.

### Bespoke WebRTC/WebSocket application

Deferred. It requires streaming audio, VAD, interruption, partial transcripts, buffering, reconnection, mobile background handling, STT/TTS and authentication. Build only if native voice, a bot relay and existing self-hosted interfaces all fail.

## Nudge architecture implications

- Keep official provider CLIs in tmux as the durable subscription boundary.
- Preserve the shared checkout default; agents may choose branches or worktrees per task.
- Keep phone gateways replaceable and northbound of a provider-neutral mailbox API.
- A possible machine-wide gateway may discover swarms and route messages while per-swarm workers retain crash isolation.
- Do not merge internet-facing connector concerns into pane monitoring or task execution without a clear security boundary.
- Keep the exit cheap: removing OpenClaw, Telegram, LibreChat or `local-mcp` must not strand tasks, replies or swarm execution.

## Focused experiments

1. Extend the existing connector contract conceptually with submit/list/read/ack/continue and test native Grok and GPT voice across separate sessions.
2. Audit MCP Agent Mail against nudge's minimal envelope and idle delivery; adopt only if it removes meaningful code without imposing its broader workflow.
3. Test a deterministic Telegram relay using phone dictation, explicit retrieval and no proactive notifications.
4. Only then trial OpenClaw as a restricted phone/router adapter, with a complete auth and quota audit and no required subscription-OAuth bridge.
5. Measure whether a machine-wide registry/gateway is useful while retaining per-swarm workers.

## Related durable work

- TASK-68: mobile voice-to-swarm and asynchronous conversational backtalk.
- TASK-69: ownership and boundary of the desktop MCP gateway.
- TASK-67: cross-swarm discovery and interaction.
- TASK-70: machine-wide supervisor versus per-swarm workers.
- DECISION-1: SQLite append-only mailbox for agent comms.
- `alt/README.md`: historical Thing-centric persistent orchestration research.

## Sources checked 2026-08-27

- OpenClaw architecture, Talk, mobile, session routing, MCP and provider-auth documentation.
- OpenAI and xAI connector documentation, supplemented by observed working local GPT/Grok voice connectivity.
- MCP Agent Mail repository documentation.
- Redis Streams documentation.
- LibreChat speech and MCP configuration documentation.
- Telegram Bot API and Discord message/voice-message documentation.
