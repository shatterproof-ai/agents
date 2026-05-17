---
name: install-shatter
description: Install the `shatter` binary, run `shatter init` in the current project, and write a guarded usage stanza into the project's primary agent doc so future agents know how to use Shatter here.
---

## Model Guidance

Recommended model: low. Narrow install workflow with explicit commands and
a fixed end-state.

## Purpose

Set up Shatter for use in a downstream project. Install the CLI, initialize
the project, and leave a durable note in the project's agent doc.

## Behavior

### 1. Install the `shatter` binary

Pick the install path based on the user's intent:

- **Continuous build (default)**: run
  ```bash
  curl -sSL https://raw.githubusercontent.com/shatterproof-ai/shatter/main/install.sh | bash
  ```
  Default install location is `~/.local/bin`. Set `INSTALL_DIR=...` for a
  different destination.
- **Pinned build for CI or reproducibility**: instead of the above, pin a
  specific tag:
  ```bash
  curl -sSL https://raw.githubusercontent.com/shatterproof-ai/shatter/main/install.sh \
    | BUILD=continuous-YYYYMMDD-HHMM-<sha> bash
  ```
- **Build from source (contributors only)**: clone the repo, install Rust
  toolchain + Node.js 22+ + Go 1.24+ + `libclang`, then run
  `cargo build --release`. Use this only when the user requests it.

Verify with:

```bash
shatter --help
```

If the binary is not on `PATH`, point the user at the install-location
hint (`~/.local/bin` by default) and stop.

### 2. Initialize the project

From the project root, run:

```bash
shatter init
```

This creates `.shatter/config.yaml` if missing. Confirm to the user that
the file now exists.

### 3. Update the project's agent doc

Run the bundled helper:

```bash
python3 scripts/update_usage_stanza.py \
  --tool shatter \
  --project-root . \
  --version "$(shatter --version 2>/dev/null | head -1)" \
  --skill run-shatter \
  --skill report-shatter-issues
```

The helper picks the destination by this order:

1. `AGENTS.md` if it exists.
2. Else `CLAUDE.md` if it exists.
3. Else create `docs/shatter-usage.md` and add a one-liner in `README.md`
   pointing at it.

The stanza is bracketed by `<!-- shatter:usage -->` and
`<!-- /shatter:usage -->`. Re-running this skill replaces the stanza in
place.

### 4. Hand off

Suggest `run-shatter` for the user's first end-to-end run; the run skill
will discover and run any integrated targets the project has.

## Out of scope

- Adding `shatter` wrappers to `package.json` / `Taskfile.yml` /
  `Makefile` (covered by `add-shatter-target`, deferred).
- CI wiring (covered by `wire-shatter-ci`, deferred).
- Diagnosing existing Shatter installs (covered by `shatter-doctor`,
  deferred).

## Required companion

- `scripts/update_usage_stanza.py` (bundled with this skill, byte-identical
  to the copy in `install-refute`)
