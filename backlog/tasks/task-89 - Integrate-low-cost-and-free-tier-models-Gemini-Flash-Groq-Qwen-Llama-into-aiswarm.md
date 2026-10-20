---
id: TASK-89
title: >-
  Integrate low-cost and free-tier models (Gemini Flash, Groq Qwen/Llama) into
  aiswarm
status: To Do
assignee: []
created_date: '2026-10-20 13:47'
updated_date: '2026-10-20 13:51'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluate and add alias definitions to swarm/models.yaml and config templates for low-cost and free-tier model backends across all 4 providers (Google AI Studio, Groq Cloud, Mistral AI, OpenRouter) driven via aider or native CLI. Covers all viable text/coding models queried directly from each provider API. These provide zero-token-cost and low-cost pay-as-you-go alternatives comparable to Claude Haiku (for graphify/extraction) and Codex Luna (for routine subtasks).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Define swarm/models.yaml alias entries for aider:gemini and aider:groq with non-interactive flags (--yes-always, --no-auto-commits)
- [ ] #2 Document environment variable loading (~/.cred/ai.sh with GEMINI_API_KEY and GROQ_API_KEY) in nudge swarm documentation
- [ ] #3 Document paid pay-as-you-go upgrade tiers for Google AI Studio and Groq Cloud when free rate limits (1.5k req/day and 14.4k req/day) need expansion
- [ ] #4 Provide a test swarm config or template with a designated lightweight/free worker pane
- [ ] #5 Include models from all providers: Google (gemini-3.8-flash, gemini-2.5-pro), Groq (qwen3.8-27b, gpt-oss-120b), Mistral (codestral-latest, mistral-code-latest), OpenRouter (cohere/north-mini-code:free, nemotron-3-super-120b:free)
<!-- AC:END -->
