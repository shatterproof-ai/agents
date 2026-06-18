---
name: refute-transform
description: Drive a single structural refactor — extract-function, move-to-file, or inline-variable — via `refute` with strict preview-then-apply discipline; confirm backend health with `refute doctor`, capture a preview diff for user review, then apply only after explicit approval and report the affected files.
---

## Model Guidance

Recommended model: mid. Procedural refactor driver with judgment on
selecting code ranges, disambiguating symbols, and interpreting backend
warnings about partial coverage.

## Purpose

Perform exactly one structural refactor in a project, gated by an
explicit preview-and-approve step. The skill must never apply an edit
the user has not seen.

These operations mirror standard LSP code actions that the supported
backends already expose: **Extract Function**, **Move to new file /
module**, and **Inline Variable**.

Supported operations:

- **extract-function** — select a contiguous range of code, give it a
  name, and replace the range with a call to the new function.
- **move-to-file** (a.k.a. move-to-module) — move a named function or
  type to a new or existing file, updating every reference.
- **inline-variable** — collapse a single-use binding by substituting
  its initializer at the use site and deleting the binding.

Supported languages: **Go** (gopls), **Rust** (rust-analyzer),
**TypeScript / JavaScript** (typescript-language-server). Not every
backend exposes every operation; the doctor support matrix is the
source of truth (see step 1).

Out of scope: renames (use `refute-rename`), Java and Kotlin,
cross-language refactors, and chaining multiple operations in one
invocation.

## Choosing the operation

Pick exactly one operation per invocation. If the user's request maps
to more than one (for example "pull this block into its own function in
a new file"), do the operations one at a time — extract first, review,
then move — never as a single combined edit.

If the requested operation is ambiguous, stop and ask which of the
three the user wants.

## Required inputs

Common to all operations:

- The **project root** (defaults to the current working directory).
- The **target file** path.

Per operation:

- **extract-function**
  - A **code range** in the target file: `START_LINE:START_COL-END_LINE:END_COL`,
    or a line range `START_LINE-END_LINE` if the backend accepts it.
  - A **new function name**.
- **move-to-file**
  - The **symbol name** (function or type) to move, optionally with a
    `file:line` hint to disambiguate.
  - The **destination file** (new or existing).
- **inline-variable**
  - The **binding** to inline, identified by name plus a `file:line`
    hint when the name is not unique in scope.

If a required input is missing or self-contradictory (for example an
empty range, or a destination identical to the source), stop and ask.

## Behavior

### 1. Confirm backend health and operation support

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

Parse the doctor output for the backend that matches the target file.
The backend must be reported `READY` **and** must list the specific
operation you intend to run (`extract-function`, `move`, or
`inline-variable`) among its usable operations.

**Refuse to proceed** when the relevant backend is:

- missing,
- out of date,
- present but reports the requested operation as unsupported.

In that case, surface the exact remediation command from the doctor
output and stop. Do not run the refactor. Point the user at
`refute-doctor` for a fuller diagnosis if needed.

### 2. Run the operation in preview mode

With a healthy backend that supports the operation, run the matching
command in preview mode. The exact subcommand and flag names are
whatever this project's pinned `refute` exposes — confirm them with
`refute <operation> --help` before relying on them, exactly as you
would for any preview-capable command. The canonical forms are:

```bash
# extract-function
refute extract-function --preview --file <PATH> \
  --range <START_LINE:START_COL-END_LINE:END_COL> --name <NEW_NAME>

# move-to-file
refute move --preview --symbol <NAME> --file <SRC> --dest <DEST_FILE>

# inline-variable
refute inline --preview --file <PATH[:LINE]> --symbol <NAME>
```

Capture both stdout (the unified diff) and stderr (backend warnings).
**Never substitute apply mode for preview**, and never invent a flag
the `--help` output does not show — if preview is unavailable for an
operation in this build, stop and report that rather than applying
blind.

If the preview command exits non-zero, report the error verbatim and
stop. Do not proceed to apply.

### 3. Show the diff and any warnings

Present to the user:

- a short header naming the operation, the target symbol or range, and
  the affected files (counted from the diff),
- the full unified diff as a fenced ```diff block (this is the artifact
  for review),
- any backend warnings from stderr, called out separately.

If the diff is empty, report "no changes produced" and stop — do not
apply.

If backend warnings indicate ambiguity, conflicts, or partial coverage
(for example: the extracted range captures a variable that escapes the
new function, the moved symbol leaves dangling references, the binding
is used more than once, generated files skipped, or build errors in the
workspace), surface them and ask the user whether to proceed before
requesting approval.

### 4. Wait for explicit approval

Ask the user to approve the diff. Acceptable approvals:

- "yes", "apply", "go ahead", or equivalent.

Anything ambiguous, conditional, or asking for changes counts as **not
approved**. Do not apply. If the user asks for a different name, range,
destination, or scope, restart from step 2 with the updated inputs.

### 5. Apply the operation

On explicit approval, re-run the same command with apply mode:

```bash
refute <operation> --apply <SAME ARGUMENTS AS PREVIEW>
```

If the apply step exits non-zero, report the error verbatim and run
`git status` so the user can see whether any partial edits landed. Do
not attempt to roll back automatically.

### 6. Confirm the edit

After a successful apply, run:

```bash
git status --short
```

Report:

- the list of changed files (from `git status`),
- a one-line summary naming the operation, for example:
  `Extracted <NEW_NAME> from <PATH> (N file(s) changed) via <backend>.`,
- a reminder that the change is unstaged — the user decides whether to
  stage, test, and commit.

## Fallback when LSP support is absent

These operations are driven through the language server's code actions.
If the backend does not expose the operation (step 1 reports it
unsupported), do **not** hand-roll the refactor by raw text
manipulation inside this skill — symbol-aware safety is the whole point.
Stop, report the gap, and point the user at `refute-doctor` and
`install-refute` to get a backend that supports it.

## Out of scope

- Symbol renames (covered by `refute-rename`).
- Combining multiple operations in one invocation.
- Renames or refactors that span multiple languages at once.
- Staging, testing, or committing the resulting edit.
- Java and Kotlin backends.
