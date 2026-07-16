---
id: TASK-27
title: Observe how backlog cli works for instruction and agent recommendations
status: To Do
assignee: []
created_date: '2026-07-16 09:28'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Perhaps we could simplify our workflow with the swarm a lot by simply using the cli to dump instructions?

i.e. 

aiswarm # get simple help
aiswarm instructions # get more help perhaps even THIS swarm specific?

I am wondering too if it would help to somehow rely on the curdir project root somehow to indicate what swarm yaml file we should use rather than typing it each time?

i.e. we could have a .swarm dir or something or a symlink .swarm.yaml to the actual yaml?

We could also move to hidden dirs as the default and like .swarm for all and that is the default dir containing all our usual stuff? That might make more sense. There are multiple thoughts here.

perhaps .aiswarm to match  our command? This might simplify some concerns earlier about "swarm" stuff being in git but kind of being a personal choice of dev harnass. 

Example:

(uv_3.12_jax) cottrell@bleepblop:~/dev/nudge$ backlog
██████╗  █████╗  █████╗ ██╗  ██╗██╗      █████╗  ██████╗    ███╗   ███╗██████╗ 
██╔══██╗██╔══██╗██╔══██╗██║ ██╔╝██║     ██╔══██╗██╔════╝    ████╗ ████║██╔══██╗
██████╦╝███████║██║  ╚═╝█████═╝ ██║     ██║  ██║██║  ██╗    ██╔████╔██║██║  ██║
██╔══██╗██╔══██║██║  ██╗██╔═██╗ ██║     ██║  ██║██║  ╚██╗   ██║╚██╔╝██║██║  ██║
██████╦╝██║  ██║╚█████╔╝██║ ╚██╗███████╗╚█████╔╝╚██████╔╝██╗██║ ╚═╝ ██║██████╔╝
╚═════╝ ╚═╝  ╚═╝ ╚════╝ ╚═╝  ╚═╝╚══════╝ ╚════╝  ╚═════╝ ╚═╝╚═╝     ╚═╝╚═════╝ 

Backlog.md v1.48.0

Common workflow:
  backlog search "query" --plain                 Search tasks, docs, and decisions
  backlog task list --plain                      List tasks
  backlog task view TASK-123 --plain             Read task context
  backlog task create "Title" -d "Description"   Create a task
  backlog board                                  Open the TUI Kanban board
  backlog browser                                Open the Web UI Kanban board

Local instructions:
  backlog instructions                           List workflow guides
  backlog instructions overview                  Required first read before answering any user request
  backlog instructions task-creation             How to search, scope, and create tasks
  backlog instructions task-execution            How to plan, update, and work through tasks
  backlog instructions task-finalization         How to verify, summarize, and finish work
  backlog instructions init-required             How to initialize Backlog.md in this directory

Command help:
  backlog <command> --help                       Show options, fields, and examples

Docs: https://backlog.md

(uv_3.12_jax) cottrell@bleepblop:~/dev/nudge$ backlog instructions
Backlog.md instructions

Start here:
  'backlog instructions overview'            Required first read before answering any user request
  'backlog <command> --help'                 Show options, fields, and examples

Guides:
  overview
    'backlog instructions overview'
      -> Required first read before answering any user request
  task-creation
    'backlog instructions task-creation'
      -> How to search, scope, and create tasks
  task-execution
    'backlog instructions task-execution'
      -> How to plan, update, and work through tasks
  task-finalization
    'backlog instructions task-finalization'
      -> How to verify, summarize, and finish work
  init-required
    'backlog instructions init-required'
      -> How to initialize Backlog.md in this directory
(uv_3.12_jax) cottrell@bleepblop:~/dev/nudge$ backlog instructions overview
## Backlog.md Overview (CLI)

This project uses Backlog.md to track features, bugs, and structured work as tasks.

### When to Use Backlog

Create a task when the work requires planning, decisions, or handoff notes.

Ask: "Do I need to think about HOW to do this?"

- Yes: search for an existing task first, then create one if needed.
- No: do the small mechanical change directly.

Create tasks for work like bug fixes that need investigation, feature work, API changes, refactors, or anything that should be reviewed as a commitment. Skip task creation for questions, explanations, quick lookups, and obvious mechanical edits.

### Start Every Request Here

Use this overview to decide what to read or run next.

Search and read before changing anything:

- `backlog search "query" --plain`
- `backlog task list --status "<todo status>" --plain`
- `backlog task list --status "<active status>" --plain`
- `backlog task list --search "login" --labels frontend,bug --limit 20 --plain`
- `backlog task view TASK-123 --plain`

### Detailed Guides

**Required: read the matching guide below before creating, executing, or finalizing tasks. Do not rely on this overview alone for these actions.** The overview only tells you when to act; the guides define the required procedure, and skipping them produces inconsistent tasks and metadata.

- `backlog instructions task-creation`
  -> Read before creating tasks: how to search, scope, and create tasks
- `backlog instructions task-execution`
  -> Read before planning or updating task work: how to plan, update, and work through tasks
- `backlog instructions task-finalization`
  -> Read before finishing tasks: how to verify, summarize, and finish tasks

Use `backlog <command> --help` before unfamiliar operations. Command help includes input fields, read/write behavior, output shape, and examples.

### Core Principle

Backlog tracks committed work: what will be built, fixed, or changed. Use the CLI for Backlog changes so metadata, file names, relationships, and history stay consistent.

Important: Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use Backlog commands so automatic metadata stays complete.
<!-- SECTION:DESCRIPTION:END -->
