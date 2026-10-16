# Human presence

`aiswarm presence` tells agents whether a human is present (`IN`) or away (`OUT`). Default auto timeout is 15 minutes (`900s`). No YAML is required.

- **`IN`**: value human time. Ask clarifying questions, seek guidance, do not leave them waiting.
- **`OUT`**: high autonomy on routine authorized tasks. Do not pause for trivial approvals. Make reasonable decisions, document choices in notes, and keep moving. Seek approval when a material architecture or design decision requires it.

```bash
aiswarm presence                              # effective, local, and global presence
aiswarm presence in                           # pin current swarm to IN
aiswarm presence out                          # pin current swarm to OUT
aiswarm presence local global                 # follow global presence (default)
aiswarm presence global in|out|auto           # set or reset global presence
aiswarm presence in --for 2h                  # temporary override with auto-expiry
```
