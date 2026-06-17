# Bifrost Opinion: Subscriptions vs APIs and Swarm Economics

## 1. The Core Economic Conflict

When orchestrating autonomous agent swarms (like the `nudge` swarm), we face a fundamental economic divergence between payment models:

| Model | Cost Structure | Constraints | Best Use Case |
|---|---|---|---|
| **Frontier APIs** (pay-as-you-go) | Linear with token usage (highly expensive in loops) | High cost (can run into thousands of dollars quickly) | High-level planning, complex reasoning, initial architecture |
| **Consumer Subscriptions** (flat-rate) | Flat monthly fee ($20/mo for Claude Pro/ChatGPT Plus) | Strict rate limits (e.g., 50 msgs / 5 hrs), UI/scraping-heavy | Iterative coding, code modification, debugging loops |
| **Local Inference** (Ollama/vLLM) | Zero marginal cost (hardware depreciation only) | Lower reasoning capability, local GPU/CPU resource limits | Syntax checking, simple tests, boilerplate generation, basic edits |

### The "API Burn" Problem
In agent loops, the context window is repeatedly re-sent on every turn. If an agent has a 50k token context (system prompts, current file, task log, workspace structure) and runs a 20-step loop to fix a bug, it consumes:
$$\text{Total Tokens} \approx 20 \times 50,000 = 1,000,000 \text{ tokens}$$
At $3.00 per million input tokens (e.g., Claude 3.5 Sonnet API), that single bug-fix run costs **$3.00**.
If a swarm of 5 agents runs continuously throughout the day doing 100 iterations, the cost scales to **$300/day ($9,000/month)**. This matches the past experiences where raw API agent swarms ran up bills of thousands of dollars.

---

## 2. Why Claude's "Swap Subscription to APIs" Idea is a Trap

Claude's recommendation to "swap subscription to APIs" is a standard developer bias toward clean, stateless, and fully supported API endpoints. While APIs make the code simpler (no tmux scraping, no process state monitoring, simple HTTP requests), they are financially unsustainable for continuous background task execution.

We **should not** force a full switch to pay-as-you-go APIs. Doing so destroys the economic feasibility of running background swarms for independent developer workflows. Instead, we must maintain **Subscription Economics** and **Local Inference Economics** as first-class citizens.

---

## 3. The Role of Bifrost: A Hybrid Gateway, Not a Monolith

Bifrost's role in the `alt/` architecture should be a **smart gateway and quota/caching layer**, not a mechanism that forces all agents to use direct raw APIs.

Here is how Bifrost can help preserve subscription economics:

### A. Routing by Role and Intelligence Cost
Bifrost should support routing requests based on the required "tier" of the agent:
* **The Planner (API Tier):** High-level decision-making requires the absolute highest intelligence (e.g., Claude 3.5 Sonnet API / Gemini 1.5 Pro API). Since planners only run occasionally to seed task graphs or handle major checkpoints, their API consumption is low and controllable.
* **The Worker (Subscription/Local Tier):** Implementing tasks (running compilers, writing tests, applying code edits) is highly repetitive and token-heavy. These should be routed to flat-rate developer subscriptions (like Claude Code CLI running under a user's subscription, or Aider via Copilot) or local models (like Qwen 2.5 Coder via Ollama).

### B. Aggressive Semantic Caching
The primary cost driver in API loops is the redundancy of sending the same system prompt, code files, and context.
* Bifrost can intercept API calls and perform **semantic caching** or use provider-native **prompt caching** (like Anthropic's Prompt Caching) to discount input tokens by up to 90%.
* For local/subscription workers, Bifrost can cache responses to avoid calling the model entirely if a sub-task query is identical.

### C. Quota Tracking and Backpressure Oracle
When worker agents run on subscription-based accounts, they inevitably hit rate limits.
* Rather than silently failing or falling back to expensive APIs (costing money), Bifrost and the orchestrator (Pulse) should detect this rate-limiting (e.g. by parsing tmux outputs or reading `~/.claude/sessions/{PID}.json` process state).
* Bifrost acts as a **backpressure oracle**, telling the Pulse: *"Claude Pro is rate-limited for the next 45 minutes. Route this implementer task to the local Qwen-2.5-Coder model, or pause execution."*

---

## 4. Keeping the Tmux Harness (Nudge's Strengths)

The original design of `nudge` (orchestrating agents in tmux panes) is actually a major asset for subscription economics. Running CLIs like `claude` (Claude Code) or browser-wrapped sessions inside tmux allows us to leverage flat-rate developer tools that aren't exposed as standard stateless APIs. 

If we move entirely to stateless APIs, we lose the ability to run these flat-rate CLI agents.

### Recommendation:
1. **Maintain the tmux harness** for worker agents to exploit flat-rate consumer subscriptions and local model CLI frontends.
2. **Use Bifrost as a hybrid proxy**: It should manage API keys for the orchestrator/planners, provide semantic caching, and act as a central quota registry tracking usage limits.
3. **Equip the Pulse with cost-aware dispatching**: The orchestrator should check Bifrost's quota state before launching a pane. If API budget is low or subscription rate limits are hit, it should dispatch to local models.
