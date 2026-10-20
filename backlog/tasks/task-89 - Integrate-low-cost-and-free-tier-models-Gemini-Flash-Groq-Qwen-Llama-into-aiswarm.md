---
id: TASK-89
title: >-
  Integrate low-cost and free-tier models (Gemini Flash, Groq Qwen/Llama) into
  aiswarm
status: To Do
assignee: []
created_date: '2026-10-20 13:47'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluate and add alias definitions to swarm/models.yaml and config templates for low-cost / free-tier model backends (Google AI Studio Gemini 3.8 Flash, Groq Cloud Qwen 3.8 27B / GPT-OSS 120B) driven via aider or native CLI. These provide zero-token-cost alternatives comparable to Claude Haiku (for graphify/extraction) and Codex Luna (for routine subtasks), with seamless paid pay-as-you-go upgrade paths when rate limits are exceeded.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Define swarm/models.yaml alias entries for aider:gemini and aider:groq with non-interactive flags (--yes-always, --no-auto-commits)
- [ ] #2 Document environment variable loading (~/.cred/ai.sh with GEMINI_API_KEY and GROQ_API_KEY) in nudge swarm documentation
- [ ] #3 Document paid pay-as-you-go upgrade tiers for Google AI Studio and Groq Cloud when free rate limits (1.5k req/day and 14.4k req/day) need expansion
- [ ] #4 Provide a test swarm config or template with a designated lightweight/free worker pane
<!-- AC:END -->
