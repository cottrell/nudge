---
id: TASK-22
title: Package aiswarm as an installable console script
status: Done
assignee: []
created_date: '2026-07-13 15:19'
updated_date: '2026-07-13 15:20'
labels: []
dependencies: []
references:
  - pyproject.toml
  - Makefile
  - README.md
  - swarm/init.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Expose aiswarm through standard Python packaging so agents and humans can call a real PATH command instead of a shell alias or repo-relative script path. Keep the source of truth in swarm/cli.py, but make the installed entrypoint the primary workflow and provide a one-command install target.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pyproject.toml defines an aiswarm console script entrypoint.
- [x] #2 Repo docs and generated swarm instructions prefer aiswarm over a repo-relative CLI path.
- [x] #3 A single install command is documented for setting up aiswarm on PATH.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added a setuptools console script for aiswarm, constrained packaging discovery to the swarm package, documented make install-aiswarm, and verified uv tool install --editable . --force installs the executable.
<!-- SECTION:FINAL_SUMMARY:END -->
