# TODO

## Native rewrite

The Python monitor works but has non-trivial startup cost and memory footprint
for something intended to run permanently alongside every agent session.

A native version (C, Zig, or Rust) would be:
- ~1MB resident vs ~20MB for Python
- instant startup
- no runtime dependency

The Python implementation defines the spec — patterns config, socket protocol,
HTTP endpoints, states. A native port is a straight translation.

**Candidate languages:**
- **C** — smallest binary, most portable, regex via `regcomp`/`regexec` or PCRE
- **Zig** — easy C interop, good stdlib, safer than C
- **Rust** — `regex` crate is excellent, good for this kind of stream processing

Pattern config would move to a file (TOML/JSON) rather than being compiled in,
so agent patterns can be updated without recompiling.
