# Similar projects

The space of “run many coding agents in parallel” is large and growing (see
[awesome-agent-orchestrators](https://github.com/andyrewlee/awesome-agent-orchestrators)).
nudge sits in a narrower slice: **config-driven tmux swarm lifecycle**, a small
**activity monitor** (`working` / `idle`), **durable log messaging delivered only
when idle**, optional **idle babysit**, and optional **backlog → free-pane** task
dispatch.

What is usually *not* the product center here (and may be elsewhere): big TUI
control planes, **one worktree per agent as the swarm model**, desktop/Electron
fleet UIs, or vendor-native agent teams.

Git worktrees are fine when an agent (or human) chooses them for a task; nudge
does not invent or require them. The default swarm is a **shared project cwd** —
coordinate via idle-gated messaging and backlog, not by forking the checkout per
pane. Peers that *do* center worktree isolation (dmux, Claude Squad, thurbox, …)
are solving a related but different problem.

### At a glance

| Project | Substrate | Summary | vs nudge |
| --- | --- | --- | --- |
| **[NTM](https://github.com/Dicklesworthstone/ntm)** | real tmux · Go | Full local control plane: spawn, dashboard, mail, safety, work graph, robot/API | Closest full-stack peer; broader operator surface |
| **[thurbox](https://github.com/Thurbeen/thurbox)** | real tmux · Rust TUI | Multi-CLI sessions, worktrees, automations, tasks, inter-session mailbox, review | Closest “productized TUI”; heavier than YAML grid + workers |
| **[dmux](https://github.com/standardagents/dmux)** | real tmux · Node | Parallel agents, **one worktree/branch per pane**, merge/PR flow | Isolation + git workflow first; not idle log gate |
| **[Claude Squad](https://github.com/smtg-ai/claude-squad)** (`cs`) | real tmux · Go TUI | Background multi-agent sessions, worktrees, diff review before apply | Session/worktree manager; not swarm log + babysit |
| **[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)** | real tmux | Hierarchy (shogun → karo → ashigaru) across many CLIs | Role tree orchestration vs declarative pane grid |
| **[Corral](https://github.com/cdknorow/corral)** | tmux + FastAPI | Self-hosted control plane for local coding agents | Server/API flavor; different packaging |
| **[herdr](https://github.com/ogulcancelik/herdr)** | own mux (Rust) | Agent-aware multiplexer, status detection, persistent workspaces | Smart terminal, not tmux YAML + log workers |
| **[tmux-ide](https://github.com/wavyrai/tmux-ide)** | real tmux | `ide.yml` layouts, agent-team templates | Layout/IDE templates; lighter orchestration loop |
| **[cmux](https://github.com/manaflow-ai/cmux)** | macOS terminal | Agent-native terminal (panes/splits), not a thin tmux wrapper | Different substrate; often compared in the same “fleet” conversation |
| **Claude Code Agent Teams** | native / tmux panes | Vendor multi-agent teams (`teammateMode`) | Claude-only product feature, not multi-provider harness |

### Closest peers (detail)

#### [NTM](https://github.com/Dicklesworthstone/ntm)

[NTM (Named Tmux Manager)](https://github.com/Dicklesworthstone/ntm) is the
closest **full-stack** cousin: local-first, tmux-centric multi-agent
orchestration for Claude / Codex / AGY / Grok. Both spawn labeled agent panes,
send work across them, and aim to make parallel coding agents manageable.

They diverge on scope and center of gravity:

| | **nudge (`aiswarm`)** | **NTM** |
| --- | --- | --- |
| **Shape** | Small Python package + C `monitor-bin`; YAML/tmuxp grids | Large Go binary; TUI dashboard/palette, REST/SSE/WS, robot CLI |
| **Core job** | Keep panes productive: activity gate → durable log delivery → optional babysit / task claim | Full local control plane: spawn, triage, mail, safety, checkpoints, pipelines |
| **Work queue** | [Backlog.md](https://github.com/Dan-Maor/backlog.md) via `aiswarm tasks` | Beads / `br` / `bv` graph triage, assign, queue-dry ideation |
| **Comms** | Per-session durable log; deliver only when pane is idle | Agent Mail + locks/reservations; human overseer mail surfaces |
| **Idle / activity** | Explicit per-pane C monitor; idle gates send | Activity/health/watch; less central to the product story |
| **Babysit** | Optional idle re-prompt loop (separate from `start` / tasks) | Not a first-class idle babysit loop |
| **Safety** | Thin (safe `tmux-send`; no policy engine) | Policy, guards, approvals |
| **Durability** | Runtime under `/tmp/nudge-swarm/…`; log cursors; backlog claims | Checkpoints, timelines, audit, pipeline resume under `.ntm/` |
| **Config** | Project `.aiswarm/config.yaml` (tmuxp-compatible + `nudge.*`) | `~/.config/ntm/` + project `.ntm/` |
| **Deps** | `tmux`, agent CLIs; optional backlog | Intentionally integration-heavy (`br`, `bv`, Agent Mail, …) |
| **When to prefer** | Lean swarm harness, idle-gated messaging, backlog dispatch | Operator dashboard, work-graph intelligence, safety/audit, APIs |

Overlap: both treat tmux as the runtime for multi-agent coding.
nudge optimizes for a small, config-driven “keep the swarm moving” loop;
NTM optimizes for a broad operator control plane around that same idea.

#### [thurbox](https://github.com/Thurbeen/thurbox)

[thurbox](https://github.com/Thurbeen/thurbox) is the closest **productized TUI**
peer: multi-CLI agents in **real tmux** (or psmux on Windows), git worktrees,
automations, built-in tasks, inter-session mailbox + wake nudges, native code
review, headless `thurbox-cli`, optional SSH hosts. Agent definitions are data
(`agents.toml`).

| | **nudge** | **thurbox** |
| --- | --- | --- |
| **Shape** | CLI + YAML; small Python + C monitor | Rust TUI + CLI; SQLite-backed session state |
| **Core job** | Declarative swarm grid + idle-gated workers | Operator TUI for many persistent agent sessions |
| **Isolation** | Shared cwd unless you arrange worktrees yourself | First-class worktrees, multi-repo sessions |
| **Comms** | Durable log, deliver on idle | Inter-session mailbox with claim/drain + wake |
| **Work** | Optional backlog claim → free pane | Built-in tasks + automations (cron/send/spawn) |
| **Activity gate** | Central (`monitor-bin` → idle delivery) | Metrics/info panel; not the same “only send when quiet” model |
| **When to prefer** | Scriptable YAML harness, idle-gated sends, backlog integration | Rich session UX, review, multi-repo, automations, Windows/SSH |

Overlap: real tmux, any coding CLI, messaging, keep many agents alive.
nudge stays smaller and more “workers around a YAML grid”; thurbox is a full
session product with review and automation surfaces.

#### [dmux](https://github.com/standardagents/dmux)

[dmux](https://github.com/standardagents/dmux) is a strong **worktree-isolation**
peer: each pane gets its own git worktree and branch; multi-agent launch, merge
and PR helpers, file browser, multi-project panes. Wide agent CLI support.

| | **nudge** | **dmux** |
| --- | --- | --- |
| **Shape** | Config-first (`aiswarm` + YAML) | Interactive TUI (`dmux`, `n` new pane) |
| **Core job** | Swarm lifecycle + idle messaging + task claim | Parallel tasks without git collisions |
| **Isolation** | Optional / external | Default (worktree + branch per pane) |
| **Comms / babysit** | Durable log + optional idle babysit | Pane management; not the same durable idle queue |
| **When to prefer** | Coordinated swarm on a shared tree + backlog | Many independent tasks, merge/PR as the endgame |

Overlap: tmux + multi-CLI parallel coding.
dmux optimizes for **branch isolation and merge UX**; nudge optimizes for
**shared-grid coordination and idle-gated delivery**.

#### [Claude Squad](https://github.com/smtg-ai/claude-squad) (`cs`)

[Claude Squad](https://github.com/smtg-ai/claude-squad) is a mature **session
manager** TUI: tmux sessions + git worktrees, background agents (Claude, Codex,
Gemini, Aider, …), attach/diff/checkout/resume, optional auto-yes.

| | **nudge** | **Claude Squad** |
| --- | --- | --- |
| **Shape** | YAML grid + CLI workers | Single TUI (`cs`) over many sessions |
| **Core job** | Keep a fixed swarm productive | Spin up/manage many background tasks |
| **Isolation** | Not the product center | Worktree per instance by default |
| **Messaging / tasks** | Durable log, babysit, backlog dispatch | Session list + diff review; less swarm mailbox |
| **When to prefer** | Long-lived multi-pane swarm with log routing | Many one-off tasks in isolated workspaces |

Overlap: tmux-backed multi-agent coding with a human overview.
Claude Squad is **instance lifecycle + worktrees**; nudge is **grid + idle
workers + optional task feed**.

#### [multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun)

[multi-agent-shogun](https://github.com/yohey-w/multi-agent-shogun) runs a
**hierarchy** of coding CLIs in tmux (shogun → karo → ashigaru), multi-provider
(Claude, Codex, Copilot, Kimi, …), with coordination meant to stay cheap
(local, not an extra LLM control plane).

| | **nudge** | **shogun** |
| --- | --- | --- |
| **Shape** | Flat YAML panes + roles via prompts/config | Explicit feudal role tree |
| **Core job** | Idle-gated swarm + backlog claim | Hierarchical parallel army |
| **When to prefer** | Declarative grid you start/stop as a unit | Role-based multi-agent theater in tmux |

### Other related tools

Status / indicators / light managers:

- [ccmanager](https://github.com/kbwo/ccmanager)
- [tallr](https://github.com/kaihochak/tallr)
- [agent-tmux-monitor](https://github.com/damelLP/agent-tmux-monitor)
- [tmuxcc](https://github.com/nyanko3141592/tmuxcc)
- [agent-deck](https://github.com/asheshgoplani/agent-deck)
- [agent-of-empires](https://github.com/njbrake/agent-of-empires)
- [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator)
- [tcmux](https://github.com/k1LoW/tcmux)

General session layout (not agent-specific):

- [tmuxp](https://tmuxp.git-pull.com/)
- [tmuxinator](https://github.com/tmuxinator/tmuxinator)
- [teamocil](https://github.com/remiprev/teamocil)
- [Zellij](https://zellij.dev/)
