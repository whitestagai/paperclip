# Agent Nightly Learning

Implementation of the nightly learning loops for Paperclip agents.
See spec: `docs/superpowers/specs/2026-05-11-agent-nightly-learning-design.md`
Plan: `docs/superpowers/plans/2026-05-12-agent-nightly-learning.md`

## Layout

- `agent-learning-trigger.sh` — main entry (modes: knowledge | lessons | decay)
- `lib/` — shared Bash functions
- `templates/` — issue-body / memory / agents.md snippets / config.example.yaml
- `launchd/` — three plists, one per schedule (01:00 / 02:00 / Sun 03:00)
- `tests/` — sandboxed Bash tests for pure-logic functions

## Install

```bash
./install.sh
```

Symlinks scripts to `~/.paperclip/scripts/`, copies the config template
to `~/.paperclip/instances/default/agent-learning.config.yaml` (only if missing),
and installs launchd plists.

The Board-API-Key secret at `~/.paperclip/instances/default/agent-learning.secret`
must exist before install.sh — create it via the CLI-auth-challenge flow
described in the plan, Task 0 Step 3.

## Uninstall

```bash
./uninstall.sh
```

Removes symlinks and launchd plists. Config, secret and vault contents are kept.

## Manual run

```bash
~/.paperclip/scripts/agent-learning-trigger.sh knowledge [--dry-run]
~/.paperclip/scripts/agent-learning-trigger.sh lessons [--dry-run]
~/.paperclip/scripts/agent-learning-trigger.sh decay [--dry-run]
```
