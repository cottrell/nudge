---
id: TASK-89
title: >-
  Integrate low-cost and free-tier models (Gemini Flash, Groq Qwen/Llama) into
  aiswarm
status: Done
assignee:
  - '@claude'
created_date: '2026-10-20 13:47'
updated_date: '2026-10-20 14:01'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Integrate low-cost and free-tier providers into aiswarm (Google AI Studio and Groq Cloud). Focus on free volume ceilings (Google: 1.5k req/day + 1M TPM; Groq: 14.4k req/day + 30 RPM) to absorb routine task loops at zero cost, with documented pay-as-you-go upgrade economics (Google ~bash.075/1M; Groq ~bash.20/1M) to seamlessly lift rate limits without breaking swarm pipelines.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Define swarm/models.yaml alias entries for aider:gemini and aider:groq with non-interactive flags (--yes-always, --no-auto-commits)
- [x] #2 Document environment variable loading (~/.cred/ai.sh with GEMINI_API_KEY and GROQ_API_KEY) in nudge swarm documentation
- [x] #3 Document paid pay-as-you-go upgrade tiers for Google AI Studio and Groq Cloud when free rate limits (1.5k req/day and 14.4k req/day) need expansion
- [x] #4 Provide a test swarm config or template with a designated lightweight/free worker pane
- [x] #5 Include models from all providers: Google (gemini-3.8-flash, gemini-2.5-pro), Groq (qwen3.8-27b, gpt-oss-120b), Mistral (codestral-latest, mistral-code-latest), OpenRouter (cohere/north-mini-code:free, nemotron-3-super-120b:free)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added aider agent type (monitor.c, common.py, cli.py), aider:* aliases, docs/models.md, swarm/templates/free-tier.yaml. Codex heavy review fixed: groq slug, nemotron slug, template load, pricing (Gemini 3.8 flash ~$0.75/M; Groq qwen ~1K RPD, not 14.4k). Groq ids verified via aider --list-models; others unverified. No quota probe/session-resume for aider. Antigravity review still pending at close.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
aider agent + 8 aider:* aliases (gemini, groq, mistral, openrouter), key loading via --env-file ~/.cred/ai.sh, docs/models.md, free-tier template. Verified: make test (180 pass), alias resolution, 'aiswarm start free-tier.yaml --dry-run'. Not live-launched; quota/idle detection is generic only.
<!-- SECTION:FINAL_SUMMARY:END -->
