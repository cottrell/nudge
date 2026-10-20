# nudge

:-)

<p align="center">
  <img src="assets/favicon-mural-droid.jpg" alt="Kratos and Bia force an idle agent-droid back to work" width="220" />
</p>

Yet another multi-agent-in-tmux setup — kept small on purpose: **comms**
(tmux-send + durable log, deliver on idle), **loops** (babysit nudges + backlog
→ free panes), and **best-effort quota** pacing. Config-driven YAML/tmuxp grids
and a tiny activity monitor (`working` / `idle`). Not a full control plane.

<p align="center">
  <img src="assets/demo.gif" alt="aiswarm demo: init, start, shell-pane sends and backlog task dispatch" width="720" />
  <br />
  <sub>Demo (3× speed): <code>aiswarm init --flavour demo</code> → start → shell-pane ops / backlog tasks · <a href="assets/demo.mp4">mp4</a></sub>
</p>

Daily driver **and** loop harness: the same panes are where you sit and work
with agents by hand (Claude, Codex, Grok, …), and where idle-gated comms /
babysit / tasks keep things moving when you step back. Personal multi-agent
workflows; works standalone.

## Design philosophy

- Shared checkout is the default. A branch or worktree is a choice, not the swarm model.
- Exit stays cheap. Git, Backlog, tmux, and provider sessions stay useful without nudge.
- Layers are optional: tmux, monitor, durable log, babysit, tasks, quota hints.
- Mechanisms stay ordinary: processes, files, SQLite, YAML, tmux, provider CLIs.
- Subscription access is the official CLI only. No OAuth, token reuse, or third-party bridges as architecture.
- Backlog and git hold the work. Nudge wakes and routes.

Primary workflow is the installed `aiswarm` command. From a repo checkout,
`python -m swarm.cli` or `python swarm/cli.py` also works.

`aiswarm` must be on `PATH`; from this repo, run `make install-aiswarm`.

```bash
aiswarm                      # workflow cheat sheet
aiswarm instructions         # agent guides index
aiswarm instructions overview
aiswarm this                 # this swarm: config + runtime.json path
aiswarm sessions             # provider session IDs (resume after a crash)
aiswarm start --resume       # relaunch panes from those IDs
aiswarm <command> --help     # flags
```

Install `aiswarm` into your `uv` tool environment:

```bash
make install-aiswarm
```

### Default config (`.aiswarm/config.yaml`)

Consumer projects: harness lives under **`.aiswarm/`** (not the Python package).

Resolution order for commands that need a config:

1. Explicit path (`aiswarm status path/to.yaml` or `-c path/to.yaml`)
2. `$AISWARM_CONFIG`
3. Walk up from cwd for **`.aiswarm/config.yaml`**

```bash
aiswarm init myproject          # writes .aiswarm/config.yaml + prompts (commit if team-shared)
aiswarm start                   # no path needed inside the project
aiswarm send 0.0 "hello"        # same
aiswarm send any "check tests"  # one eligible idle pane receives it
aiswarm send heavy "refactor"   # one idle pane in category `heavy`
aiswarm send --at +2h 0.2 "check progress"  # deferred delivery (ISO timestamp or +Nh/+Nm/+Ns)
aiswarm status .aiswarm/config.yaml   # explicit path still works
```

Note: in **this** repo, `./swarm/` is the Python package. The live harness is
`.aiswarm/config.yaml`.

States: `unknown` `working` `idle`

## Workflow

```bash
# 1. Create a starter config and AGENTS note (once per project)
aiswarm init <project>

# 2. Turn on the swarm (tmux session + panes + monitors + worker)
#    Changing pane counts on a live session means recreate, not re-run start.
aiswarm start

# 3. Optional loops. Neither starts with `aiswarm start`.
aiswarm babysit start          # panes with babysit.enabled
aiswarm tasks start            # backlog → free panes

# 4. Full teardown
aiswarm stop
```

Send, categories, and handoff: [docs/workflow.md](docs/workflow.md).

## Docs

- [Workflow](docs/workflow.md) — send, categories, scheduled delivery, handoff
- [Config](docs/config.md) — YAML grid, workers, resume, runtime paths
- [Presence](docs/presence.md) — `aiswarm presence`
- [Tasks](docs/tasks.md) — backlog dispatcher, chase, healthcheck
- [Quota pacing](docs/quota.md) — babysit EMA
- [Free-tier models](docs/models.md) — aider panes on Gemini, Groq, Mistral, OpenRouter
- [Monitor](docs/monitor.md) — activity states, fixtures, debug
- [Similar projects](docs/similar-projects.md) — NTM, thurbox, dmux, Claude Squad, herdr, and others

## Build and test

```bash
make build
make test
make test-c
make test-swarm
```

Python helpers live in `pyproject.toml`:

```bash
uv sync
```

## Rough edges

- Changing pane counts or layout after `start` requires a full session recreate (`start` is create-oriented, not a declarative grid update)
- Monitor is activity-based only (not semantic agent status); quiet long jobs can look idle, busy idle-screen redraws can look working
- Quota EMA pacing is noisy when multiple swarms share one provider quota (overestimates, so nudges slow down; usually the safe direction)
- `usage` and quota reporting are a best-effort operator hint, not a hard scheduler

See `backlog/tasks/` for planned work. Contributions welcome via issues or PRs (see `AGENTS.md`).
