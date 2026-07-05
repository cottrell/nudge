Please review the following changes to the nudge project (babysit / swarm worker logic).

**Context (user's model):** One IO loop per pane. Comms group (poll + message drain on idle) is always on. Babysit group (prompt nudges, EMA pacing, clears, forced nudges) is independently toggleable on/off.

**Tickets:**
- TASK-13: Refactor babysit control API (fix start_comms misuse for "babysit stop"). New: ensure_workers, apply_babysit, disable_babysit, stop_workers.
- TASK-14: Make babysit group dynamically toggleable inside the single worker without process restart (re-read spec).
- TASK-16: Fix runtime.json advertisement so external UIs don't falsely think babysit is running.

**Commits:**
- de3f580 (main refactor + dynamic + runtime fix)
- e731c37 (naming/docs follow-up)

**Key files to inspect:**
- babysit.py (added _current_prompts() that reloads from spec; refresh every loop)
- swarm/babysitctl.py (new public functions, _prompts_only_change for hot-update, shims)
- swarm/cli.py (updated dispatch and help text)
- swarm/common.py (build_runtime_map now derives has_* from deployed spec; improved self-awareness text)
- swarm/topology.py (status legend and start comment)
- test_swarm.py (updated tests)

**Specific review questions:**
1. Is the control surface now simple and matches "comms always + babysit toggleable"?
2. Does the dynamic spec reload in the worker look correct and safe (no missed state, handles enable after start as comms, disable while running)?
3. Any issues with status display, runtime.json for consumers, force nudges, EMA, clear_every, or comms delivery after toggles?
4. Edge cases: worker not yet started, full stop, --no-action, dry-run, stale specs/pids?
5. Naming and docs improvements sufficient?

Please be direct about bugs or remaining confusion. LGTM + notes or specific problems appreciated.
