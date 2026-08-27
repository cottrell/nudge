---
id: doc-5
title: 'Voice, subscription and agent communications research'
type: other
created_date: '2026-08-27 10:42'
updated_date: '2026-08-27 11:36'
tags:
  - voice
  - architecture
  - mcp
  - subscriptions
  - comms
  - mobile-web
  - tmux
  - security
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
## Phone-first web UI over official CLI sessions

A browser conversation UI may replace muxpod as the phone interaction layer without replacing tmux, nudge, or official provider CLIs. This is materially different from Open WebUI/LibreChat: the backend is a PTY attached to the real CLI, not an API model endpoint.

```text
phone browser
  -> project/session picker
  -> chat view or raw terminal
  -> tmux-backed official provider CLI
  -> CLI transcript and/or nudge conversational mailbox
```

The browser can add push-to-talk dictation through the Web Speech API or ordinary phone keyboard dictation, and read selected responses using browser/device speech synthesis. Browser SpeechRecognition may use a platform service and has uneven browser support, so it must be tested on the actual phone; it is not automatically local. SpeechSynthesis generally uses device voices. A local Whisper/Piper fallback can remain optional.

Relevant existing projects found:

- Agent Tmux Web: private mobile browser control surface for tmux-backed CLIs; explicitly hosts no AI service, sends keys to tmux, captures output, switches sessions and supports phone-oriented TTY/raw views.
- AgentDeck: xterm.js/node-pty/tmux transport plus an optional structured chat view derived from official CLI transcript files; supports mobile tabs, session history, send/interrupt and resume for several CLIs.
- agmux: tmux-backed browser PTYs, readiness detection, inactive-session restoration and task-provider hooks; broader and less phone/chat focused.
- WeTTY/ttyd/xterm.js: generic browser terminal building blocks, credible fallback if agent-specific products impose too much workflow.

This surface could offer two modes:

1. Direct session mode: choose a project/session, dictate into the actual CLI, and listen to selected transcript messages.
2. Routed conversation mode: speak naturally to one nudge router, which records conversation IDs and dispatches to swarms; later explicitly retrieve and discuss replies without selecting a pane.

Direct mode solves cramped phone tmux interaction immediately. Routed mode solves session selection and asynchronous correlation. They can coexist, with a raw terminal escape hatch for permissions, pickers and unusual TUI states.

Evaluation should prefer adopting or lightly extending an existing browser-over-tmux project. Required checks include phone UX, voice input/output, generic Grok/GPT/Gemini/Codex CLI support, transcript extraction versus fragile screen scraping, existing nudge session discovery, authentication, private IPv6/mesh access, disconnect recovery, and ease of removal. Do not expose a terminal-control service directly to the public internet.

Sources:

- https://github.com/antonlobanovskiy/agent-tmux-web
- https://github.com/AliceLJY/agentdeck
- https://github.com/rjprins/agmux
- https://github.com/butlerx/wetty
- https://github.com/xtermjs/xterm.js
- https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
## Exact browser-to-tmux communication choices

Tmux is a byte transport, not a conversational protocol. Sending input is straightforward; identifying a clean completed reply is the hard boundary.

### Input path

For an existing nudge pane, the browser sends `{conversation_id, turn_id, swarm, pane, text}` to the local web backend. The backend appends through `aiswarm send` so nudge can retain the message and deliver it when the pane is idle. Raw interactive controls such as permission prompts can use the existing safe tmux-send wrapper or an attached PTY path. Do not use raw `tmux send-keys` from application code.

### Output option 1: raw terminal stream

Attach or capture the pane and stream terminal bytes to xterm.js. This is generic and gives exact visibility, but ANSI/TUI redraws are not a reliable assistant-message boundary and should not be fed blindly to TTS. Best for the first direct-control prototype and as an escape hatch.

### Output option 2: provider transcript adapter

Read the official CLI's local conversation/session record and emit structured user/assistant messages. AgentDeck uses this pattern. It gives the best chat and TTS experience but requires a small adapter per provider and may break when provider storage formats change. The adapter remains optional; raw terminal access must still work.

### Output option 3: explicit nudge reply

Include a reply address such as `browser:<conversation_id>` and ask the receiving agent to send its final conversational response back through the nudge mailbox. This is provider-neutral and durable, but depends on agent cooperation until reply tooling is installed automatically. Backlog remains the result channel for tracked work; the mailbox reply is the short conversational response.

### Output option 4: idle plus capture heuristic

Record pane output before sending, wait for the monitor to transition working then idle, capture the delta and attempt to extract the answer. This is acceptable only as a disposable prototype. Quiet commands, redraws, permissions and truncated scrollback make it unsuitable as the durable protocol.

Recommended sequence:

1. Prototype direct mode with selected existing pane, `aiswarm send`, monitor state and raw browser output.
2. Add browser push-to-talk or VAD and local/platform STT; keep text visible and editable before automatic sending initially.
3. Add selected-response speech synthesis only after obtaining structured reply text through a transcript adapter or explicit mailbox reply.
4. Add barge-in by stopping browser audio and cancelling only the current browser speech playback; do not interrupt the underlying coding agent unless the user explicitly requests it.
5. Test backgrounding, reconnect, duplicate turn IDs, microphone permission and audio playback on the actual phone.

Gemini's estimate of 100-150 backend lines is plausible for a disposable audio echo or one-shot prompt demo, not for reliable multi-session conversation. VAD itself is available through `@ricky0123/vad-web`; the complexity lies in mobile lifecycle and trustworthy agent-response extraction.
## Agent Tmux Web trial security note (2026-08-27)

Trial source: `~/dev/agent-tmux-web` at upstream commit `aa13d56d8901ac2ec11784ba30941cf6a6d4115d` (v0.1.26). Production build started as transient user service `agent-tmux-web-trial.service` on `[::]:16174`, with mandatory random token and Codex app-server autostart disabled. It discovered existing nudge-created tmux sessions without recreating them. HTTP API returned 401 without the token and 200 with it.

Treat the token as a remote-shell credential. The application is not nudge-scoped: authenticated callers can inspect and type into all tmux sessions owned by the Unix user, create or destroy sessions, upload files, attach raw terminals and invoke configured CLI launchers. Yggdrasil provides an encrypted mesh path and difficult-to-guess cryptographic addressing, but does not replace application authorization; any reachable mesh peer may attempt the service. Do not expose this service directly to the public internet.

Current trial URL is HTTP. Phone keyboard dictation should remain available because it belongs to the phone keyboard, but browser `getUserMedia`, Web Speech recognition and in-page VAD generally require a trusted secure context. Add trusted HTTPS before evaluating in-page microphone features. Query-string tokens are convenient but can remain in history/screenshots; prefer a future login/session cookie or header flow if the trial is retained.

Dependency audit initially found a high-severity runtime `ws` issue; the local trial updated `ws` to 8.21.3. Remaining audit findings are primarily build/development dependencies, so the trial uses the compiled production server rather than Vite development mode. Upstream tests pass 269/270 after the local dependency update; the one failure is its source-registry dependency manifest expecting the original `ws` entry.
