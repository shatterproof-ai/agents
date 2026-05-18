---
name: add-shatter-target
description: Wire a project so `run-shatter` discovers and runs it as an integrated target by adding a `shatter` wrapper to `package.json`, `Taskfile.yml`, or `Makefile`. Detects supported-language targets and command surfaces, drafts diffs, writes on approval, and verifies integration.
---

## Model Guidance

Recommended model: low. The skill is procedural: detect, draft, diff,
write, verify. No qualitative judgment required.

## Purpose

For downstream users of Shatter. Add the minimal project-native wrapper
that turns a target from `not integrated` into `integrated` so that
`run-shatter` will run it. One wrapper per target; never overwrite an
existing `shatter` wrapper without explicit confirmation.

## What "integrated" means

A target is `integrated` when its root directory defines a wrapper named
`shatter` on one of these surfaces (in priority order):

1. `package.json` with `scripts.shatter` (invoked via the package manager
   hinted by lockfile or `packageManager` field).
2. `Taskfile.yml` with a `shatter:` task (invoked via `task shatter`).
3. `Makefile` with a `shatter:` target plus `.PHONY: shatter`.

`run-shatter`'s bundled `scripts/run_targets.py` is the source of truth
for which surfaces count. This skill produces wrappers that match those
detection rules byte-for-byte.

## Workflow

### 1. Discover targets and current integration

From the repo root:

```bash
python3 scripts/run_targets.py --root . --json
```

If `run_targets.py` is not on the working path, it ships alongside the
`run-shatter` skill in the Shatter plugin (typically in the plugin
cache under `.../skills/run-shatter/scripts/run_targets.py`). The script
prints a JSON payload with one entry per discovered target including
`root`, `languages`, `status` (`integrated` or `not_integrated`), and
`reason`. Focus on targets where `status == "not_integrated"`.

If the helper is genuinely unavailable, fall back to a manual check at
each language marker (`Cargo.toml`, `go.mod`, `package.json`): a target
is integrated iff one of the wrapper surfaces above is present.

### 2. Detect the command surface for each unintegrated target

For each target root, pick the surface in this order:

- **`package.json` present** → add a `scripts.shatter` entry.
  Determine the package manager by:
  - `packageManager` field (`pnpm`, `yarn`, `bun`, `npm`); else
  - lockfile: `pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn,
    `bun.lock`/`bun.lockb` → bun; else
  - default to npm.
- **`Taskfile.yml` present** → add a `shatter:` task.
- **`Makefile` present and no `Taskfile.yml`** → add a `shatter:` target
  with `.PHONY: shatter`. (Taskfile takes precedence when both exist.)
- **None of the above** → skip; surface this back to the user with a
  short note that no supported wrapper surface exists at that root.

If multiple surfaces exist, prefer `package.json` for Node/TS targets,
otherwise prefer Taskfile over Makefile. Only add one wrapper per
target.

### 3. Draft the minimal wrapper

The wrapper command itself should be `shatter` (no extra flags) unless
the user asks for something specific. Keep the addition surgical: do
not reformat surrounding content, reorder keys, or alter unrelated
fields.

#### `package.json`

Add or merge a single key under `"scripts"`:

```json
{
  "scripts": {
    "shatter": "shatter"
  }
}
```

If `scripts` does not exist, create it. If `scripts.shatter` already
exists with a different value, stop and ask the user before
overwriting.

#### `Taskfile.yml`

Append (or merge into the existing `tasks:` map) a task. The
`run_targets.py` detector matches a `shatter:` key indented by 2+
spaces, so place it under `tasks:`:

```yaml
tasks:
  shatter:
    desc: Run Shatter on this target.
    cmds:
      - shatter
```

If a top-level `version: '3'` is absent and the file is empty/new, write
the full minimal Taskfile:

```yaml
version: '3'

tasks:
  shatter:
    desc: Run Shatter on this target.
    cmds:
      - shatter
```

#### `Makefile`

Append:

```make
.PHONY: shatter
shatter:
	shatter
```

Use a literal TAB for the recipe line; Make will reject spaces.

### 4. Show the diff before writing

For every file you intend to change, show the user a unified diff of the
proposed edit and wait for approval. Group all proposed edits in one
review so the user can approve or reject as a batch or per file. Do not
write until the user approves.

### 5. Write on approval

Apply only the approved edits. Preserve the trailing newline of each
file. For `package.json`, keep existing indentation (2-space or 4-space)
and key ordering; insert `"shatter"` alphabetically within `scripts` if
that matches the existing style, otherwise append.

### 6. Verify integration

Re-run:

```bash
python3 scripts/run_targets.py --root . --json
```

Confirm each newly wired target now reports `"status": "integrated"`
with the expected `surface.type` (`package-json-scripts`, `taskfile`, or
— for Makefile — note that the v1 detector in `run_targets.py` does not
yet recognize `Makefile`, so a Makefile-only target will still report
`not_integrated`; in that case verify manually with `make -n shatter`
and tell the user the wrapper is in place but discovery support is
pending).

Report a one-line summary per target: `wired (<surface>)`, `skipped (no
supported surface)`, or `already integrated`.

## Out of scope

- Installing the `shatter` binary (covered by `install-shatter`).
- Authoring Shatter specs or fuzzing configuration.
- CI wiring (covered by `wire-shatter-ci`, deferred).
- Editing wrappers that already exist with non-default content — ask the
  user first.

## Required companion

None bundled. The skill relies on the `run_targets.py` helper that
ships with the `run-shatter` skill in the same plugin for verification.
