---
name: refute-doctor
description: Run `refute doctor` for a project, parse the support matrix, report the status of each language's backend and the available refactoring operations, and recommend the exact remediation command for each problem.
---

## Model Guidance

Recommended model: mid. Procedural diagnostic with light judgment on
which language entries actually matter for this project.

## Purpose

Tell the user whether Refute is healthy for the languages this project
actually uses, and exactly what to fix when it is not.

## Required inputs

- The path to the project root (defaults to the current working
  directory).

## Behavior

### 1. Run the doctor

From the project root:

```bash
refute doctor
```

If the project uses Refute as a Go-tool dependency rather than a global
binary, run instead:

```bash
go tool refute doctor
```

Capture the output. If the command is missing, point the user at
`install-refute` and stop.

### 2. Detect relevant languages

Inspect the project root for these markers:

- `go.mod` → Go
- `Cargo.toml` → Rust
- `package.json` → TypeScript / JavaScript

Restrict the report to the languages present in the project. Mention but
do not block on languages the doctor reports for which the project does
not use.

### 3. Report

For each language present in the project, report:

- backend status (ready / missing / out of date / extension missing)
- which refactoring operations are currently usable, named individually so a
  caller knows whether a specific transform will run. The operations the
  backends expose are `rename`, `extract-function`, `move` (move-to-file), and
  `inline-variable`, plus reference search. Coverage varies by backend — list
  exactly the operations the doctor reports for each one rather than assuming
  the full set.
- the exact remediation command, taken from the doctor output, when the
  backend is not ready

Use this shape:

```
## Refute Health

- Go (gopls): READY at v0.x.y — rename, extract-function, move,
  inline-variable, reference search usable
- Rust (rust-analyzer): MISSING
  Fix: rustup component add rust-analyzer
- TypeScript: BACKEND OUT OF DATE
  Fix: npm install -g typescript-language-server@latest
```

When a backend is `READY` but the doctor lists only a subset of operations
(for example a backend that supports `rename` and `extract-function` but not
`move`), report the usable subset and call out the missing operations
explicitly, so a caller such as `refute-transform` knows up front which
structural refactors it can and cannot run.

### 4. Summary

Close with a one-line summary: "Refute is ready for the languages this
project uses" or "Refute is blocked on N backends — see above".

## Out of scope

- Installing backends (covered by `install-refute`).
- Performing refactorings (renames via `refute-rename`; extract-function,
  move-to-file, and inline-variable via `refute-transform`).
- Pinning versions (covered by `pin-refute`).
