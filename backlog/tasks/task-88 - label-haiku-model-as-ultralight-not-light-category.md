---
id: TASK-88
title: label haiku model as ultralight not light category
status: Done
assignee: []
created_date: '2026-10-16 13:57'
updated_date: '2026-10-30 11:18'
labels: []
dependencies: []
---

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Resolved against the original premise. User judgement: haiku is not ultralight; ultralight means local tiny-GPU models and the weakest free-tier endpoints. swarm/models.yaml now maps claude:light -> haiku as the single claude low alias (the claude:ultralight entry is removed; .aiswarm/config.yaml, 2x2.yaml, 3x2.yaml and test_swarm.py already used claude:light, so nothing else changed). Tier semantics documented in docs/models.md and the aiswarm instructions overview guide: tiers are not a permission gate, the one implication is that ultralight output is a proposal needing review before Done.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Rejected the rename: haiku stays claude:light, ultralight reserved for local/free-tier models. Removed the duplicate claude:ultralight alias and documented tier meaning in docs/models.md + instructions overview. Verified by rendering the overview guide and grepping for remaining ultralight/claude:light references.
<!-- SECTION:FINAL_SUMMARY:END -->
