---
name: refute-rename
description: Drive a single symbol-aware rename via `refute rename` with strict preview-then-apply discipline — confirm backend health with `refute doctor`, capture a preview diff for user review, then apply only after explicit approval and report the affected files.
---

## Model Guidance

Recommended model: mid. Procedural refactor driver with judgment on
disambiguating symbols and interpreting backend warnings.

## Purpose

Perform exactly one symbol rename in a project, gated by an explicit
preview-and-approve step. The skill must never apply an edit the user
has not seen.

Supported languages: **Go** (gopls), **Rust** (rust-analyzer),
**TypeScript / JavaScript** (typescript-language-server).
Out of scope: Java, Kotlin, cross-language renames, multi-step
refactors.

## Required inputs

- The **old symbol name** (current identifier).
- The **new symbol name** (target identifier).
- Optionally, a **source file hint** (path, or `path:line`) to
  disambiguate when the same name appears in multiple scopes.
- The **project root** (defaults to the current working directory).

If the new name is missing or identical to the old name, stop and ask.

## Behavior

### 1. Confirm backend health

Before touching code, run:

```bash
refute doctor
```

(or `go tool refute doctor` if the project pins Refute as a Go-tool
dependency.)

Detect the relevant language from project markers:

- `go.mod` → Go (gopls)
- `Cargo.toml` → Rust (rust-analyzer)
- `package.json` / `tsconfig.json` → TypeScript

Parse the doctor output for the backend that matches the target file
(or all relevant ones if no file hint was given). The backend must be
reported `READY` and must list `rename` among its usable operations.

**Refuse to proceed** when the relevant backend is:

- missing,
- out of date,
- present but reports the `rename` operation as unsupported.

In that case, surface the exact remediation command from the doctor
output and stop. Do not run `refute rename`. Point the user at
`refute-doctor` for a fuller diagnosis if needed.

### 2. Run the rename in preview mode

With a healthy backend, run:

```bash
refute rename --preview <OLD> <NEW> [--file <PATH[:LINE]>]
```

Capture both stdout (the unified diff) and stderr (backend warnings).
If the CLI uses a different preview flag in this project's pinned
version, infer it from `refute rename --help` — but never substitute
apply mode for preview.

If the preview command exits non-zero, report the error verbatim and
stop. Do not proceed to apply.

### 3. Show the diff and any warnings

Present to the user:

- a short header naming the symbol and the affected files (counted
  from the diff),
- the full unified diff as a fenced ```diff block (this is the
  artifact for review),
- any backend warnings from stderr, called out separately.

If the diff is empty, report "no matches" and stop — do not apply.

If backend warnings indicate ambiguity, conflicts, or partial coverage
(for example: shadowed names, generated files skipped, build errors in
the workspace), surface them and ask the user whether to proceed
before requesting approval.

### 4. Wait for explicit approval

Ask the user to approve the diff. Acceptable approvals:

- "yes", "apply", "go ahead", or equivalent.

Anything ambiguous, conditional, or asking for changes counts as
**not approved**. Do not apply. If the user asks for a different new
name or a narrower scope, restart from step 2 with the updated inputs.

### 5. Apply the rename

On explicit approval, re-run with apply mode:

```bash
refute rename --apply <OLD> <NEW> [--file <PATH[:LINE]>]
```

If the apply step exits non-zero, report the error verbatim and run
`git status` so the user can see whether any partial edits landed.
Do not attempt to roll back automatically.

### 6. Confirm the edit

After a successful apply, run:

```bash
git status --short
```

Report:

- the list of changed files (from `git status`),
- a one-line summary: `Renamed <OLD> → <NEW> across N file(s) via
  <backend>.`,
- a reminder that the change is unstaged — the user decides whether
  to stage, test, and commit.

## Out of scope

- Multi-step planned refactors (extract function, inline, move).
- Renames that span multiple languages in one invocation.
- Staging, testing, or committing the resulting edit.
- Java and Kotlin backends.
