# Beads Workflow Context

## 🚨 Session Close Protocol
Before saying "done" or "complete":
1. `git status` — check what changed
2. `git add <files>` — stage code changes
3. `git commit -m "..."` — commit
4. `git push` — push if an upstream exists

## Core Commands
- `bd ready` — show issues ready to work (no blockers)
- `bd show <id>` — detailed issue view with dependencies
- `bd create --title="..." --description="..." --type=task|bug|feature --priority=2` — new issue
- `bd update <id> --claim` — claim work
- `bd close <id>` — mark complete
- `bd dep add <issue> <depends-on>` — add dependency

## Rules
- Use beads for ALL task tracking. Do NOT use TodoWrite, TaskCreate, or markdown TODO files.
- Create the beads issue BEFORE writing code; mark in_progress when starting.
- Use `bd remember "insight"` for persistent knowledge across sessions; search with `bd memories <keyword>`.

Run `bd memories` for persistent notes.
Run `bd prime --full` for the complete command reference.
