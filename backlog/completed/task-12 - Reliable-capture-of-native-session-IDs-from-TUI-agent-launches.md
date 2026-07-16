---
id: TASK-12
title: Reliable capture of native session IDs from TUI agent launches for alt/ Things
status: Done
assignee: []
created_date: '2026-06-18 13:00'
updated_date: '2026-07-16 13:09'
labels:
  - alt
  - launch
  - session-id
  - orchestration
dependencies:
  - TASK-10
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Blocker for alt/ prompt-driven Things**: When launching a TUI agent (claude, codex, grok, etc.) via --prompt / fire-and-forget path, we must reliably capture its *native* session_id (the one usable for resume, identification, or revival) immediately after launch, along with pid if available. This must be stored in the Thing's node record before the agent starts working.

Current system uses tmux pane targets primarily. Alt needs the harness-native identifiers because sessions can be headless or resumed independently of tmux.

### Decision (no universal clean solution)

We do the best available method per provider. There is no single clean pattern.

- **claude**: Supports `--session-id <uuid>` at launch time (including with `-p`). We generate a UUID and pass it via `--session-id`. Cleanest case. (We still defensively read the on-disk file in case it differs.)
- **codex**: `codex exec` always prints `session id: <uuid>` in the initial banner. We launch, capture stdout, and parse the ID from the first lines.
- **grok**: No way found to supply an ID at creation. After launching `grok -p ...`, take the newest subdirectory name under `~/.grok/sessions/<url-encoded-cwd>/`. This is scoped to the cwd and avoids the global `sessions list` race.
- **agy**: No clean creation-time flag or banner. After `agy -p ...`, take the newest `session-*-<uuid>` file created under `~/.gemini/tmp` or `~/.cache` (time-bounded after launch). Fallback to first UUID appearing in the captured output.

We always record the SID we actually obtained for the node so it can later be resumed/forked using the provider's native mechanism.

### Requirements (updated)
- Generate or capture a native session ID during/after the non-interactive launch.
- Record it (plus pid if available) in the per-node record under `alt/state/things/<thing>/`.
- Must work for `-p` / `exec` style non-interactive launches.
- Prefer mechanical capture (banner parse or fs observation) over asking the model to report the ID inside the task prompt.

### Implementation
- `alt/bin/launch-child.sh` implements the per-provider logic above.
- Node file written on start (with the SID), then updated on finish.
- Later continuation uses the provider's resume/fork (e.g. `claude --resume $sid --fork-session`, `codex exec resume $sid`, etc.).

Status: basic implementation done per the decisions above. inotify-based watching would be a nice follow-up for the fs-based agents.

### Synthetic fallback
Only for unknown agents: `synthetic-<ts>-$$`.

### Related
- See also TASK-10 (session launch metadata schema).
- inotify-based watching (instead of polling) would be a further improvement for the fs cases.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-07-16 hygiene: marking Done; alt/ is side path, not main aiswarm line.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Basic per-provider native session ID capture implemented in alt/bin/launch-child.sh (claude --session-id, codex banner parse, grok/agy fs observation). Ticket notes already said basic impl done. Optional inotify follow-up not scheduled. Closed in hygiene 2026-07-16.
<!-- SECTION:FINAL_SUMMARY:END -->
