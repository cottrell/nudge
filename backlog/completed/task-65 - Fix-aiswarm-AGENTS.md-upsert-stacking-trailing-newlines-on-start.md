---
id: TASK-65
title: Fix aiswarm AGENTS.md upsert stacking trailing newlines on start
status: Done
assignee:
  - '@antigravity'
created_date: '2026-08-08 13:48'
updated_date: '2026-08-09 07:43'
labels:
  - aiswarm
  - agents.md
  - bug
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

`aiswarm` start/init rewrites `AGENTS.md` via `swarm/init.py` → `write_agents_block` → `upsert_agents_text`.

When an AISWARM block is followed by other content (almost always the Backlog.md managed guidelines block), the upsert is **not idempotent**: each call adds one more trailing newline at EOF. Dirty `AGENTS.md` (`+\n` only) appears across many repos after swarm start.

Root: join path uses `head.rstrip()`, `tail.lstrip("\n")`, `"\n\n".join(parts) + "\n"`, which changes the file even when the AISWARM body is unchanged, and accumulates EOF newlines.

## Reproduce

```python
from swarm.init import upsert_agents_text, agent_block
block = agent_block("demo")
text = "# Project\n\n" + block + "\n<!-- BACKLOG.MD GUIDELINES START -->\nx\n<!-- BACKLOG.MD GUIDELINES END -->\n"
for i in range(5):
    text, action = upsert_agents_text(text, block)
    # action stays "updated"; trailing NL count increases each pass
```

## Scope

- Fix `upsert_agents_text` (and any related start path) so identical block body ⇒ `unchanged` and no file write.
- Do not grow trailing newlines across repeated start/init.
- Leave Backlog-managed section intact.
- Add regression test in `test_swarm.py`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Repeated upsert/start with AISWARM + following Backlog block does not change AGENTS.md when AISWARM body is unchanged
- [x] #2 Repeated upsert does not increase trailing newline count at EOF
- [x] #3 Regression test covers AISWARM-then-Backlog layout and multi-pass stability
- [x] #4 aiswarm start/init still inserts or updates AISWARM block correctly when content actually changes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Modify  in  to strip leading and trailing whitespace/newlines from head and tail sections when replacing or checking the AISWARM block, producing clean idempotency with a single trailing EOF newline.
2. Add regression test  in .
3. Verify test suite with cc -O2 -Wno-unused-result -o monitor-bin monitor.c -lpthread
bash test_c.sh
status: {"state":"working"}
tail:   {"line":"⠙ Thinking…"}
done
uv run pytest test_monitor.py -v
============================= test session starts ==============================
platform linux -- Python 3.14.0, pytest-9.0.2, pluggy-1.6.0 -- ~/dev/nudge/.venv/bin/python
cachedir: .pytest_cache
rootdir: ~/dev/nudge
configfile: pyproject.toml
collecting ... collected 30 items

test_monitor.py::test_initial_state_is_unknown PASSED                    [  3%]
test_monitor.py::test_any_agent_output_marks_working[claude] PASSED      [  6%]
test_monitor.py::test_any_agent_output_marks_working[codex] PASSED       [ 10%]
test_monitor.py::test_any_agent_output_marks_working[copilot] PASSED     [ 13%]
test_monitor.py::test_any_agent_output_marks_working[gemini] PASSED      [ 16%]
test_monitor.py::test_any_agent_output_marks_working[grok] PASSED        [ 20%]
test_monitor.py::test_any_agent_output_marks_working[vibe] PASSED        [ 23%]
test_monitor.py::test_any_agent_output_marks_working[qwen] PASSED        [ 26%]
test_monitor.py::test_any_agent_output_marks_working[antigravity] PASSED [ 30%]
test_monitor.py::test_content_does_not_change_activity_semantics[\u276f ] PASSED [ 33%]
test_monitor.py::test_content_does_not_change_activity_semantics[-- INSERT -- \u23f5\u23f5 bypass permissions on] PASSED [ 36%]
test_monitor.py::test_content_does_not_change_activity_semantics[\u25d0 medium \xb7 /effort] PASSED [ 40%]
test_monitor.py::test_content_does_not_change_activity_semantics[\u273b Crunched for 18s] PASSED [ 43%]
test_monitor.py::test_content_does_not_change_activity_semantics[Error 429: Too Many Requests] PASSED [ 46%]
test_monitor.py::test_content_does_not_change_activity_semantics[\x1b]0;\u2733 Claude Code\x07] PASSED [ 50%]
test_monitor.py::test_quiet_timeout_marks_idle PASSED                    [ 53%]
test_monitor.py::test_new_activity_returns_idle_to_working PASSED        [ 56%]
test_monitor.py::test_repeated_activity_extends_timeout PASSED           [ 60%]
test_monitor.py::test_blank_output_is_activity PASSED                    [ 63%]
test_monitor.py::test_query_log_tail_and_unknown_command PASSED          [ 66%]
test_monitor.py::test_query_log_bounds_long_escaped_lines PASSED         [ 70%]
test_monitor.py::test_query_tail_max_control_char_line_stays_alive PASSED [ 73%]
test_monitor.py::test_cli_rejects_unknown_agent PASSED                   [ 76%]
test_monitor.py::test_cli_rejects_invalid_idle_timeout[0] PASSED         [ 80%]
test_monitor.py::test_cli_rejects_invalid_idle_timeout[-1] PASSED        [ 83%]
test_monitor.py::test_cli_rejects_invalid_idle_timeout[nan] PASSED       [ 86%]
test_monitor.py::test_cli_help_lists_agents_and_idle_timeout PASSED      [ 90%]
test_monitor.py::test_fixture_replay_becomes_idle_after_quiet PASSED     [ 93%]
test_monitor.py::test_state_log_records_activity_and_timeout PASSED      [ 96%]
test_monitor.py::test_debug_writes_raw_lines PASSED                      [100%]

============================== 30 passed in 4.12s ==============================
uv run pytest test_swarm.py -v
============================= test session starts ==============================
platform linux -- Python 3.14.0, pytest-9.0.2, pluggy-1.6.0 -- ~/dev/nudge/.venv/bin/python
cachedir: .pytest_cache
rootdir: ~/dev/nudge
configfile: pyproject.toml
collecting ... collected 102 items

test_swarm.py::test_load_config_resolves_prompt_file PASSED              [  0%]
test_swarm.py::test_load_config_rejects_short_prompt_only_babysit PASSED [  1%]
test_swarm.py::test_swarm_init_default_3x2_layout PASSED                 [  2%]
test_swarm.py::test_swarm_init_demo_flavour_layout PASSED                [  3%]
test_swarm.py::test_swarm_init_creates_config_prompts_and_agents_block PASSED [  4%]
test_swarm.py::test_babysit_stop_workers_tolerates_empty_pid_file PASSED [  5%]
test_swarm.py::test_restart_worker_preserves_runtime_and_comms_state PASSED [  6%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[missing] PASSED [  7%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[malformed] PASSED [  8%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[stale] PASSED [  9%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[unexpected] PASSED [ 10%]
test_swarm.py::test_tasks_status_tolerates_garbage_pid_file PASSED       [ 11%]
test_swarm.py::test_resolve_config_walk_up_env_and_explicit PASSED       [ 12%]
test_swarm.py::test_cli_send_token_split PASSED                          [ 13%]
test_swarm.py::test_cli_bare_and_instructions PASSED                     [ 14%]
test_swarm.py::test_swarm_init_does_not_duplicate_agents_block PASSED    [ 15%]
test_swarm.py::test_agents_block_upsert_and_remove PASSED                [ 16%]
test_swarm.py::test_agents_block_upsert_idempotency_with_following_backlog_block PASSED [ 17%]
test_swarm.py::test_cli_help_prints_probed_model_commands PASSED         [ 18%]
test_swarm.py::test_babysit_log_nudge_includes_target PASSED             [ 19%]
test_swarm.py::test_load_config_multiple_panes PASSED                    [ 20%]
test_swarm.py::test_load_config_allows_non_agent_pane_when_monitor_disabled PASSED [ 21%]
test_swarm.py::test_load_config_rejects_babysit_without_monitor PASSED   [ 22%]
test_swarm.py::test_load_config_supports_long_and_short_babysit_prompts PASSED [ 23%]
test_swarm.py::test_load_config_supports_clear_every PASSED              [ 24%]
test_swarm.py::test_start_invokes_grid_monitor_and_command PASSED        [ 25%]
test_swarm.py::test_start_dry_run_writes_runtime_notes PASSED            [ 26%]
test_swarm.py::test_setup_grid_allows_new_session_to_expand PASSED       [ 27%]
test_swarm.py::test_babysit_start_updates_pane_spec_without_per_pane_process PASSED [ 28%]
test_swarm.py::test_tasks_start_toggles_session_worker_group PASSED      [ 29%]
test_swarm.py::test_pane_worker_ema_spec_controls_next_wait PASSED       [ 30%]
test_swarm.py::test_pane_worker_tick_preserves_underscore_session PASSED [ 31%]
test_swarm.py::test_pane_spec_reloads_only_after_mtime_change PASSED     [ 32%]
test_swarm.py::test_stop_workers_accepts_panespec_list PASSED            [ 33%]
test_swarm.py::test_swarm_status_reports_window_command_and_monitor PASSED [ 34%]
test_swarm.py::test_swarm_status_brief_reports_compact_states PASSED     [ 35%]
test_swarm.py::test_swarm_status_reports_tasks_state_and_heartbeat PASSED [ 36%]
test_swarm.py::test_swarm_status_reports_inactive_tasks_worker[None-False-stopped] PASSED [ 37%]
test_swarm.py::test_swarm_status_reports_inactive_tasks_worker[123-False-stale] PASSED [ 38%]
test_swarm.py::test_status_lines_handles_missing_window PASSED           [ 39%]
test_swarm.py::test_shell_prefixed_command_sets_ps1_prefix PASSED        [ 40%]
test_swarm.py::test_runtime_map_contains_only_derived_runtime_paths PASSED [ 41%]
test_swarm.py::test_swarm_status_brief_includes_babysit_countdown PASSED [ 42%]
test_swarm.py::test_swarm_status_brief_shows_stopped_when_babysit_not_running PASSED [ 43%]
test_swarm.py::test_swarm_status_marks_unreachable_monitor_socket PASSED [ 44%]
test_swarm.py::test_this_text_points_at_runtime_map PASSED               [ 45%]
test_swarm.py::test_comms_defaults_to_monitor PASSED                     [ 46%]
test_swarm.py::test_comms_helpers PASSED                                 [ 47%]
test_swarm.py::test_usage_scraper_timeout_cleans_exact_tmux_session PASSED [ 48%]
test_swarm.py::test_comms_end_to_end_plain_pane_no_agent PASSED          [ 49%]
test_swarm.py::test_broadcast_targets_monitored_panes_by_default PASSED  [ 50%]
test_swarm.py::test_broadcast_can_include_nonmonitored_agents PASSED     [ 50%]
test_swarm.py::test_broadcast_rejects_empty_message PASSED               [ 51%]
test_swarm.py::test_cli_status_watch_dispatches_to_watch_status PASSED   [ 52%]
test_swarm.py::test_cli_short_options_dispatch PASSED                    [ 53%]
test_swarm.py::test_cli_stop_dispatches_to_babysit_and_tmux_stop PASSED  [ 54%]
test_swarm.py::test_cli_worker_restart_does_not_stop_tmux PASSED         [ 55%]
test_swarm.py::test_cli_babysit_status_dispatches PASSED                 [ 56%]
test_swarm.py::test_cli_babysit_stop_dispatches_to_disable_babysit PASSED [ 57%]
test_swarm.py::test_load_config_tasks_defaults_and_pane_enable PASSED    [ 58%]
test_swarm.py::test_load_config_tasks_ingest_in_progress_explicit PASSED [ 59%]
test_swarm.py::test_load_config_tasks_ingest_defaults_to_to_do_and_in_progress PASSED [ 60%]
test_swarm.py::test_load_config_rejects_tasks_without_monitor PASSED     [ 61%]
test_swarm.py::test_parse_task_list_json_priority_and_status PASSED      [ 62%]
test_swarm.py::test_build_task_prompt_includes_claim_and_complete_instructions PASSED [ 63%]
test_swarm.py::test_load_config_min_chase_secs_override PASSED           [ 64%]
test_swarm.py::test_chase_due_respects_min_interval PASSED               [ 65%]
test_swarm.py::test_chase_assigned_skips_when_throttled PASSED           [ 66%]
test_swarm.py::test_load_config_skip_assignees_default_empty_and_legacy PASSED [ 67%]
test_swarm.py::test_load_config_tasks_complete_statuses PASSED           [ 68%]
test_swarm.py::test_load_config_tasks_complete_statuses_rejects_empty PASSED [ 69%]
test_swarm.py::test_dependency_gate_blocks_any_incomplete_dep PASSED     [ 70%]
test_swarm.py::test_dependency_gate_finds_task_moved_to_completed PASSED [ 71%]
test_swarm.py::test_dependency_gate_reports_genuinely_missing_task PASSED [ 72%]
test_swarm.py::test_complete_statuses_non_default_shared_by_gate_and_assignment PASSED [ 73%]
test_swarm.py::test_tasks_status_labels_blocked_candidates PASSED        [ 74%]
test_swarm.py::test_task_skipped_for_claim_skip_assignees PASSED         [ 75%]
test_swarm.py::test_dispatch_skips_blocked_claim_until_dependency_done PASSED [ 76%]
test_swarm.py::test_chase_blocks_once_for_open_dependency_then_resumes PASSED [ 77%]
test_swarm.py::test_dispatch_once_dry_run_claims_without_side_effects PASSED [ 78%]
test_swarm.py::test_claim_failure_does_not_save_assignment PASSED        [ 79%]
test_swarm.py::test_delivery_failure_keeps_assignment_for_chase PASSED   [ 80%]
test_swarm.py::test_healthcheck_pong_ignores_consumer_ack PASSED         [ 81%]
test_swarm.py::test_pane_respawn_argv_splits_shell_command PASSED        [ 82%]
test_swarm.py::test_respawn_task_pane_uses_split_argv PASSED             [ 83%]
test_swarm.py::test_healthcheck_probe_then_respawn_is_bounded PASSED     [ 84%]
test_swarm.py::test_claim_logs_and_skips_when_task_detail_unavailable PASSED [ 85%]
test_swarm.py::test_healthcheck_dry_run_does_not_respawn_or_probe PASSED [ 86%]
test_swarm.py::test_require_idle_rejects_unknown_monitor_state PASSED    [ 87%]
test_swarm.py::test_dispatch_skips_claim_and_chase_when_monitor_socket_missing PASSED [ 88%]
test_swarm.py::test_chase_skips_when_monitor_socket_missing PASSED       [ 89%]
test_swarm.py::test_save_state_atomic_rename_no_partial_writes PASSED    [ 90%]
test_swarm.py::test_cli_tasks_once_and_status_dispatch PASSED            [ 91%]
test_swarm.py::test_cli_this_command PASSED                              [ 92%]
test_swarm.py::test_recover_assignments_from_backlog_empty_state_finds_existing_claims PASSED [ 93%]
test_swarm.py::test_recover_assignments_dry_run_does_not_save PASSED     [ 94%]
test_swarm.py::test_recover_assignments_does_not_override_existing_local_assignments PASSED [ 95%]
test_swarm.py::test_broadcast_via_log_filtering_and_warning PASSED       [ 96%]
test_swarm.py::test_dispatch_once_backlog_call_count_independent_of_candidate_count PASSED [ 97%]
test_swarm.py::test_todo_task_assigned_to_our_pane_is_dispatched_as_new_claim PASSED [ 98%]
test_swarm.py::test_claim_matches_later_preassigned_pane_before_unmatched_pane PASSED [ 99%]
test_swarm.py::test_claim_prioritizes_preassigned_before_unassigned_with_max_inflight PASSED [100%]

============================= 102 passed in 1.91s ==============================.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed  in  and added regression tests in . Passed 102/102 pytest tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Updated  in  so repeated upserts with following blocks (like Backlog.md guidelines) do not stack trailing newlines or register spurious changes. Added regression test  in  and verified via cc -O2 -Wno-unused-result -o monitor-bin monitor.c -lpthread
bash test_c.sh
status: {"state":"working"}
tail:   {"line":"⠙ Thinking…"}
done
uv run pytest test_monitor.py -v
============================= test session starts ==============================
platform linux -- Python 3.14.0, pytest-9.0.2, pluggy-1.6.0 -- ~/dev/nudge/.venv/bin/python
cachedir: .pytest_cache
rootdir: ~/dev/nudge
configfile: pyproject.toml
collecting ... collected 30 items

test_monitor.py::test_initial_state_is_unknown PASSED                    [  3%]
test_monitor.py::test_any_agent_output_marks_working[claude] PASSED      [  6%]
test_monitor.py::test_any_agent_output_marks_working[codex] PASSED       [ 10%]
test_monitor.py::test_any_agent_output_marks_working[copilot] PASSED     [ 13%]
test_monitor.py::test_any_agent_output_marks_working[gemini] PASSED      [ 16%]
test_monitor.py::test_any_agent_output_marks_working[grok] PASSED        [ 20%]
test_monitor.py::test_any_agent_output_marks_working[vibe] PASSED        [ 23%]
test_monitor.py::test_any_agent_output_marks_working[qwen] PASSED        [ 26%]
test_monitor.py::test_any_agent_output_marks_working[antigravity] PASSED [ 30%]
test_monitor.py::test_content_does_not_change_activity_semantics[\u276f ] PASSED [ 33%]
test_monitor.py::test_content_does_not_change_activity_semantics[-- INSERT -- \u23f5\u23f5 bypass permissions on] PASSED [ 36%]
test_monitor.py::test_content_does_not_change_activity_semantics[\u25d0 medium \xb7 /effort] PASSED [ 40%]
test_monitor.py::test_content_does_not_change_activity_semantics[\u273b Crunched for 18s] PASSED [ 43%]
test_monitor.py::test_content_does_not_change_activity_semantics[Error 429: Too Many Requests] PASSED [ 46%]
test_monitor.py::test_content_does_not_change_activity_semantics[\x1b]0;\u2733 Claude Code\x07] PASSED [ 50%]
test_monitor.py::test_quiet_timeout_marks_idle PASSED                    [ 53%]
test_monitor.py::test_new_activity_returns_idle_to_working PASSED        [ 56%]
test_monitor.py::test_repeated_activity_extends_timeout PASSED           [ 60%]
test_monitor.py::test_blank_output_is_activity PASSED                    [ 63%]
test_monitor.py::test_query_log_tail_and_unknown_command PASSED          [ 66%]
test_monitor.py::test_query_log_bounds_long_escaped_lines PASSED         [ 70%]
test_monitor.py::test_query_tail_max_control_char_line_stays_alive PASSED [ 73%]
test_monitor.py::test_cli_rejects_unknown_agent PASSED                   [ 76%]
test_monitor.py::test_cli_rejects_invalid_idle_timeout[0] PASSED         [ 80%]
test_monitor.py::test_cli_rejects_invalid_idle_timeout[-1] PASSED        [ 83%]
test_monitor.py::test_cli_rejects_invalid_idle_timeout[nan] PASSED       [ 86%]
test_monitor.py::test_cli_help_lists_agents_and_idle_timeout PASSED      [ 90%]
test_monitor.py::test_fixture_replay_becomes_idle_after_quiet PASSED     [ 93%]
test_monitor.py::test_state_log_records_activity_and_timeout PASSED      [ 96%]
test_monitor.py::test_debug_writes_raw_lines PASSED                      [100%]

============================== 30 passed in 4.14s ==============================
uv run pytest test_swarm.py -v
============================= test session starts ==============================
platform linux -- Python 3.14.0, pytest-9.0.2, pluggy-1.6.0 -- ~/dev/nudge/.venv/bin/python
cachedir: .pytest_cache
rootdir: ~/dev/nudge
configfile: pyproject.toml
collecting ... collected 102 items

test_swarm.py::test_load_config_resolves_prompt_file PASSED              [  0%]
test_swarm.py::test_load_config_rejects_short_prompt_only_babysit PASSED [  1%]
test_swarm.py::test_swarm_init_default_3x2_layout PASSED                 [  2%]
test_swarm.py::test_swarm_init_demo_flavour_layout PASSED                [  3%]
test_swarm.py::test_swarm_init_creates_config_prompts_and_agents_block PASSED [  4%]
test_swarm.py::test_babysit_stop_workers_tolerates_empty_pid_file PASSED [  5%]
test_swarm.py::test_restart_worker_preserves_runtime_and_comms_state PASSED [  6%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[missing] PASSED [  7%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[malformed] PASSED [  8%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[stale] PASSED [  9%]
test_swarm.py::test_restart_worker_fails_safely_for_invalid_pid_state[unexpected] PASSED [ 10%]
test_swarm.py::test_tasks_status_tolerates_garbage_pid_file PASSED       [ 11%]
test_swarm.py::test_resolve_config_walk_up_env_and_explicit PASSED       [ 12%]
test_swarm.py::test_cli_send_token_split PASSED                          [ 13%]
test_swarm.py::test_cli_bare_and_instructions PASSED                     [ 14%]
test_swarm.py::test_swarm_init_does_not_duplicate_agents_block PASSED    [ 15%]
test_swarm.py::test_agents_block_upsert_and_remove PASSED                [ 16%]
test_swarm.py::test_agents_block_upsert_idempotency_with_following_backlog_block PASSED [ 17%]
test_swarm.py::test_cli_help_prints_probed_model_commands PASSED         [ 18%]
test_swarm.py::test_babysit_log_nudge_includes_target PASSED             [ 19%]
test_swarm.py::test_load_config_multiple_panes PASSED                    [ 20%]
test_swarm.py::test_load_config_allows_non_agent_pane_when_monitor_disabled PASSED [ 21%]
test_swarm.py::test_load_config_rejects_babysit_without_monitor PASSED   [ 22%]
test_swarm.py::test_load_config_supports_long_and_short_babysit_prompts PASSED [ 23%]
test_swarm.py::test_load_config_supports_clear_every PASSED              [ 24%]
test_swarm.py::test_start_invokes_grid_monitor_and_command PASSED        [ 25%]
test_swarm.py::test_start_dry_run_writes_runtime_notes PASSED            [ 26%]
test_swarm.py::test_setup_grid_allows_new_session_to_expand PASSED       [ 27%]
test_swarm.py::test_babysit_start_updates_pane_spec_without_per_pane_process PASSED [ 28%]
test_swarm.py::test_tasks_start_toggles_session_worker_group PASSED      [ 29%]
test_swarm.py::test_pane_worker_ema_spec_controls_next_wait PASSED       [ 30%]
test_swarm.py::test_pane_worker_tick_preserves_underscore_session PASSED [ 31%]
test_swarm.py::test_pane_spec_reloads_only_after_mtime_change PASSED     [ 32%]
test_swarm.py::test_stop_workers_accepts_panespec_list PASSED            [ 33%]
test_swarm.py::test_swarm_status_reports_window_command_and_monitor PASSED [ 34%]
test_swarm.py::test_swarm_status_brief_reports_compact_states PASSED     [ 35%]
test_swarm.py::test_swarm_status_reports_tasks_state_and_heartbeat PASSED [ 36%]
test_swarm.py::test_swarm_status_reports_inactive_tasks_worker[None-False-stopped] PASSED [ 37%]
test_swarm.py::test_swarm_status_reports_inactive_tasks_worker[123-False-stale] PASSED [ 38%]
test_swarm.py::test_status_lines_handles_missing_window PASSED           [ 39%]
test_swarm.py::test_shell_prefixed_command_sets_ps1_prefix PASSED        [ 40%]
test_swarm.py::test_runtime_map_contains_only_derived_runtime_paths PASSED [ 41%]
test_swarm.py::test_swarm_status_brief_includes_babysit_countdown PASSED [ 42%]
test_swarm.py::test_swarm_status_brief_shows_stopped_when_babysit_not_running PASSED [ 43%]
test_swarm.py::test_swarm_status_marks_unreachable_monitor_socket PASSED [ 44%]
test_swarm.py::test_this_text_points_at_runtime_map PASSED               [ 45%]
test_swarm.py::test_comms_defaults_to_monitor PASSED                     [ 46%]
test_swarm.py::test_comms_helpers PASSED                                 [ 47%]
test_swarm.py::test_usage_scraper_timeout_cleans_exact_tmux_session PASSED [ 48%]
test_swarm.py::test_comms_end_to_end_plain_pane_no_agent PASSED          [ 49%]
test_swarm.py::test_broadcast_targets_monitored_panes_by_default PASSED  [ 50%]
test_swarm.py::test_broadcast_can_include_nonmonitored_agents PASSED     [ 50%]
test_swarm.py::test_broadcast_rejects_empty_message PASSED               [ 51%]
test_swarm.py::test_cli_status_watch_dispatches_to_watch_status PASSED   [ 52%]
test_swarm.py::test_cli_short_options_dispatch PASSED                    [ 53%]
test_swarm.py::test_cli_stop_dispatches_to_babysit_and_tmux_stop PASSED  [ 54%]
test_swarm.py::test_cli_worker_restart_does_not_stop_tmux PASSED         [ 55%]
test_swarm.py::test_cli_babysit_status_dispatches PASSED                 [ 56%]
test_swarm.py::test_cli_babysit_stop_dispatches_to_disable_babysit PASSED [ 57%]
test_swarm.py::test_load_config_tasks_defaults_and_pane_enable PASSED    [ 58%]
test_swarm.py::test_load_config_tasks_ingest_in_progress_explicit PASSED [ 59%]
test_swarm.py::test_load_config_tasks_ingest_defaults_to_to_do_and_in_progress PASSED [ 60%]
test_swarm.py::test_load_config_rejects_tasks_without_monitor PASSED     [ 61%]
test_swarm.py::test_parse_task_list_json_priority_and_status PASSED      [ 62%]
test_swarm.py::test_build_task_prompt_includes_claim_and_complete_instructions PASSED [ 63%]
test_swarm.py::test_load_config_min_chase_secs_override PASSED           [ 64%]
test_swarm.py::test_chase_due_respects_min_interval PASSED               [ 65%]
test_swarm.py::test_chase_assigned_skips_when_throttled PASSED           [ 66%]
test_swarm.py::test_load_config_skip_assignees_default_empty_and_legacy PASSED [ 67%]
test_swarm.py::test_load_config_tasks_complete_statuses PASSED           [ 68%]
test_swarm.py::test_load_config_tasks_complete_statuses_rejects_empty PASSED [ 69%]
test_swarm.py::test_dependency_gate_blocks_any_incomplete_dep PASSED     [ 70%]
test_swarm.py::test_dependency_gate_finds_task_moved_to_completed PASSED [ 71%]
test_swarm.py::test_dependency_gate_reports_genuinely_missing_task PASSED [ 72%]
test_swarm.py::test_complete_statuses_non_default_shared_by_gate_and_assignment PASSED [ 73%]
test_swarm.py::test_tasks_status_labels_blocked_candidates PASSED        [ 74%]
test_swarm.py::test_task_skipped_for_claim_skip_assignees PASSED         [ 75%]
test_swarm.py::test_dispatch_skips_blocked_claim_until_dependency_done PASSED [ 76%]
test_swarm.py::test_chase_blocks_once_for_open_dependency_then_resumes PASSED [ 77%]
test_swarm.py::test_dispatch_once_dry_run_claims_without_side_effects PASSED [ 78%]
test_swarm.py::test_claim_failure_does_not_save_assignment PASSED        [ 79%]
test_swarm.py::test_delivery_failure_keeps_assignment_for_chase PASSED   [ 80%]
test_swarm.py::test_healthcheck_pong_ignores_consumer_ack PASSED         [ 81%]
test_swarm.py::test_pane_respawn_argv_splits_shell_command PASSED        [ 82%]
test_swarm.py::test_respawn_task_pane_uses_split_argv PASSED             [ 83%]
test_swarm.py::test_healthcheck_probe_then_respawn_is_bounded PASSED     [ 84%]
test_swarm.py::test_claim_logs_and_skips_when_task_detail_unavailable PASSED [ 85%]
test_swarm.py::test_healthcheck_dry_run_does_not_respawn_or_probe PASSED [ 86%]
test_swarm.py::test_require_idle_rejects_unknown_monitor_state PASSED    [ 87%]
test_swarm.py::test_dispatch_skips_claim_and_chase_when_monitor_socket_missing PASSED [ 88%]
test_swarm.py::test_chase_skips_when_monitor_socket_missing PASSED       [ 89%]
test_swarm.py::test_save_state_atomic_rename_no_partial_writes PASSED    [ 90%]
test_swarm.py::test_cli_tasks_once_and_status_dispatch PASSED            [ 91%]
test_swarm.py::test_cli_this_command PASSED                              [ 92%]
test_swarm.py::test_recover_assignments_from_backlog_empty_state_finds_existing_claims PASSED [ 93%]
test_swarm.py::test_recover_assignments_dry_run_does_not_save PASSED     [ 94%]
test_swarm.py::test_recover_assignments_does_not_override_existing_local_assignments PASSED [ 95%]
test_swarm.py::test_broadcast_via_log_filtering_and_warning PASSED       [ 96%]
test_swarm.py::test_dispatch_once_backlog_call_count_independent_of_candidate_count PASSED [ 97%]
test_swarm.py::test_todo_task_assigned_to_our_pane_is_dispatched_as_new_claim PASSED [ 98%]
test_swarm.py::test_claim_matches_later_preassigned_pane_before_unmatched_pane PASSED [ 99%]
test_swarm.py::test_claim_prioritizes_preassigned_before_unassigned_with_max_inflight PASSED [100%]

============================= 102 passed in 1.95s ============================== (102 tests passed).
<!-- SECTION:FINAL_SUMMARY:END -->
