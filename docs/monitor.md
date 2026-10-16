# Monitor

`monitor-bin` is the only monitor. It reports activity, not semantic agent status. Any pane output means `working` until the quiet timeout. Quiet long jobs can look idle. Busy idle-screen redraws can look working.

`grok` additionally parses OSC terminal-title updates as a fast path. A title of exactly `grok` flips to `idle` immediately. A leftover task-description title (for example `"TASK-123 ... - grok"`) stays `working` until the quiet timeout.

Low-level helpers, rarely needed by hand: `attach.sh` (monitor attach to a pane), `tmux-send` (safe text plus Enter).

```bash
MONITOR_DEBUG=1 ./attach.sh mysession claude
MONITOR_STATE_LOG=1 ./attach.sh mysession claude
MONITOR_IDLE_SECS=20 ./attach.sh mysession claude
```

- `MONITOR_DEBUG=1` writes raw lines to `/tmp/<session>_<window-pane>.raw`
- `MONITOR_STATE_LOG=1` writes transitions to `/tmp/<session>_<window-pane>.state.log`
- `MONITOR_IDLE_SECS` is the quiet period before `idle` (default: 10)

## Capture fixtures

Fixture replay tests depend on real captured agent output in `fixtures/*_capture.txt`. Fixtures exercise real terminal byte streams. Re-capture when replay tests expose an input-handling issue or fixtures go stale, not on a fixed schedule.

```bash
make capture AGENT=claude DUR=60
make capture_codex DUR=60
make capture_copilot DUR=60
make capture_gemini DUR=60
make capture_antigravity DUR=60
make capture_vibe DUR=60
make capture_qwen DUR=60
make capture_grok DUR=60
make capture_all DUR=60
```
