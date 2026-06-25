---
name: install-refute
description: Install the `refute` binary and the LSP backends for the languages used in the current project, verify the install, and write a guarded usage stanza into the project's primary agent doc.
---

## Model Guidance

Recommended model: low. Narrow install workflow with explicit commands and
a fixed end-state.

## Purpose

Set up Refute for use in a downstream project. Detect the languages
present in the project, install the correct LSP backends for those
languages, and leave a durable note in the project's agent doc.

## Behavior

### 1. Detect target languages

Inspect the project root for these markers and record the languages
present:

- `go.mod` → Go
- `Cargo.toml` → Rust
- `package.json` → TypeScript / JavaScript

If none are present, ask the user which language to target; do not guess.

### 2. Install `refute`

Pick the install path based on the project:

- **Go project, Go 1.24+ (preferred)**: run
  ```bash
  go get -tool github.com/shatterproof-ai/refute/cmd/refute@latest
  ```
  Verify with `go tool refute version`. Pinning a concrete release tag is
  handled by the separate `pin-refute` skill once it ships.
- **Personal shell use (non-Go project, user wants a global binary)**:
  ```bash
  go install github.com/shatterproof-ai/refute/cmd/refute@latest
  ```
  Verify with `refute version`.
- **Build from source (rare; user requested)**: clone the repo and
  `go build ./cmd/refute`.

Refuse to install if Go is not on `PATH`; point the user at the official
Go install docs and stop.

### 3. Install backends for the project's languages

For each detected language, install the matching backend if missing:

- Go (always for a Go project):
  ```bash
  go install golang.org/x/tools/gopls@latest
  ```
- Rust:
  ```bash
  rustup component add rust-analyzer
  ```
- TypeScript:
  ```bash
  npm install -g typescript-language-server typescript
  ```

Skip backends for languages the project does not use.

### 4. Verify

Run `refute version` (or `go tool refute version`) and confirm the output.

### 5. Update the project's agent doc

Run the bundled helper:

```bash
python3 scripts/update_usage_stanza.py \
  --tool refute \
  --project-root . \
  --version "$(refute version 2>/dev/null | head -1 || go tool refute version 2>/dev/null | head -1)" \
  --backend gopls \
  --backend rust-analyzer \
  --backend typescript-language-server \
  --skill refute-doctor
```

Pass only the `--backend` flags for backends that were actually installed.

The helper picks the destination by this order:

1. `AGENTS.md` if it exists.
2. Else `CLAUDE.md` if it exists.
3. Else create `docs/refute-usage.md` and add a one-liner in `README.md`
   pointing at it.

The stanza is bracketed by `<!-- refute:usage -->` and
`<!-- /refute:usage -->`. Re-running this skill replaces the stanza in
place.

### 6. Hand off to `refute-doctor`

Tell the user to run `refute-doctor` next to verify the install is fully
working for the project's languages.

## Out of scope

- Pinning to a specific release (covered by `pin-refute`).
- Performing any refactoring (renames via `refute-rename`; extract-function,
  move-to-file, and inline-variable via `refute-transform`).
- Installing language toolchains that the project already requires (Go
  itself, Node.js, rustup) — assumed present.

## Required companion

- `scripts/update_usage_stanza.py` (bundled with this skill, byte-identical
  to the copy in `install-shatter`)
