# TODO

## Completed

### Native Rewrite (C)

The C implementation (`monitor.c`) is now the primary backend:
- ~1MB binary with no runtime dependencies
- Instant startup
- Activity-based `unknown`/`working`/`idle` state
- Signal handling for cleanup (SIGINT, SIGTERM)
- Proper JSON escaping for control characters

### Python Backend Status

Python (`monitor.py`) is the **reference implementation and test oracle**:
- Defines expected activity and quiet-time behavior
- Used by fixture replay tests to verify C parity
- Should be kept in sync with C for state changes
- Not used in production (C is the runtime backend)

## Open Issues

### Edge Cases to Watch

1. **Silent work** — Commands that emit no output longer than the idle timeout appear idle.

2. **Continuous redraws** — An idle CLI that keeps emitting terminal updates appears working.

3. **Race conditions** — The `examples/launch-2pane.sh` retry loop helps but doesn't eliminate all timing issues with socket readiness.

## Future Enhancements

- Additional agents (cursor, windsurf, etc.)
- Optional first-party state sources where CLIs expose reliable structured status
- More layout recipes beyond `tiled` while keeping `rows`/`cols` explicit in config
- Replace `babysit-manager.sh` with the YAML-driven swarm path once apply/reconcile semantics settle
