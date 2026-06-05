# Alt: Minimal Session-Based Swarm (Bifrost + ClawTeam)

## Goal

Transition from long-running agents (nudge swarm) to simplest possible resumable agent session workflows with subagents also resumable. All triggerable either by human, agent or some script/IO loop.

Get a feel for a "cross-agent agent" workflow using the simplest possible setup: **Bifrost** for the gateway and **ClawTeam** for orchestration.

## Core Abstraction: "The Thing"
A "Thing" is simply an **Agent Session Graph**.
- **Trigger:** A prompt (e.g., "Deal with task-123" or "Refactor this file").
- **Persistence:** Bound to a `session_id`.
- **Composition:** A "Thing" can spawn sub-agents to handle specific parts of the prompt, creating a session DAG.

## Minimal Components

### 1. Bifrost (The Gateway)
Acts as a simple, high-performance proxy to manage rate limits and provides a single endpoint for all agents.

### 2. ClawTeam (The Logic)
Provides the ability for an agent to spawn other agents. It manages the `session_id` and the context handoff between the caller and the spawned sub-agent.

### 3. Dispatcher (The Entry Point)
A simple script: `./dispatch.sh "prompt" [session_id]`
- **No ID:** Starts a new session via ClawTeam + Bifrost.
- **With ID:** Resumes the existing session.

## Why this works
- **Stateless Infrastructure:** The dispatcher and scripts don't need to know *what* the agent is doing, only *which* session it belongs to.
- **Optional Backlog:** While we can record results in `backlog/`, the "Thing" exists independently as a session graph.
- **Local + Remote:** Bifrost allows us to mix Ollama (local) with Claude/Gemini (frontier) seamlessly.

## Getting Started (The "Feel" Test)
1. Run Bifrost locally.
2. Use ClawTeam to dispatch a multi-step prompt.
3. Observe how ClawTeam spawns a sub-agent and how the `session_id` allows us to track the work.
