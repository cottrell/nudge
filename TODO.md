# TODO

## Completed

### Native Rewrite (C)

The C implementation (`monitor.c`) is now the primary backend:
- ~1MB binary with no runtime dependencies
- Instant startup
- Full feature parity with Python reference implementation
- Signal handling for cleanup (SIGINT, SIGTERM)
- Proper JSON escaping for control characters
- Complete ANSI escape sequence stripping

### Python Backend Status

Python (`monitor.py`) is the **reference implementation and test oracle**:
- Defines expected behavior for state classification
- Used by `test_fixture_replay_c_matches_python_final_state` to verify C parity
- Should be kept in sync with C for pattern changes
- Not used in production (C is the runtime backend)

## Open Issues

### Edge Cases to Watch

1. **Agent output format changes** — When agent CLI output changes, patterns may need updates. Re-capture fixtures with `make capture_<agent>` and verify tests pass.

2. **UTF-8 handling** — The C code validates braille UTF-8 sequences but doesn't fully validate all Unicode. Malformed input could cause issues.

3. **Race conditions** — The `launch-2pane.sh` retry loop helps but doesn't eliminate all timing issues with socket readiness.

4. **Pattern gaps** — Some agents may have unclassified states. Add patterns as new output formats are observed.

5. **ANSI stripping completeness** — The C stripper handles common sequences but may miss obscure terminal control codes.

## Future Enhancements

- **Config-driven orchestration** — YAML/JSON config for launching multiple agents:
  ```yaml
  agents:
    - name: claude_main
      target: myproject:0.0
      agent: claude
      babysit: true
      interval: 600
    - name: gemini_review
      target: myproject:0.1
      agent: gemini
      babysit: false
  ```
  Then `./launch-all` reads config and spins everything up.

- Pattern config file (JSON/TOML) to avoid recompiling for pattern updates
- Additional agents (cursor, windsurf, etc.)
- Enhanced state detection (e.g., "waiting for user input" vs "idle")
