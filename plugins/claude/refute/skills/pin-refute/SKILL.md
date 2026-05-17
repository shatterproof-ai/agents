---
name: pin-refute
description: Pin `refute` as a project-managed dependency at a concrete release tag so collaborators and CI use a known version, via the Go-tool path on Go 1.24+ projects or a project-local release binary otherwise.
---

## Model Guidance

Recommended model: low. Narrow pinning workflow with explicit commands
and a fixed end-state.

## Purpose

Pin `refute` to a concrete release for the current project so every
collaborator and CI run uses the same version. Floating tags
(`@latest`, `@main`, continuous build tags) are refused.

## Behavior

### 1. Require a concrete release tag

Ask the user for the version to pin, or accept one passed in. The tag
must be a released semver tag like `v0.1.3`.

Refuse and stop if the user supplies:

- `@latest`
- `@main`, `@master`, `@HEAD`, or any branch name
- A continuous-build tag (e.g., tags containing `-dev`, `-nightly`,
  `-rc`, `-pre`, `-snapshot`, or a bare commit SHA). Warn the user
  that these move or are not durable, and require they pick a real
  release tag.

If unsure which tag is current, point the user at
`https://github.com/shatterproof-ai/refute/releases` and stop.

### 2. Detect the install path

Inspect the project root:

- If `go.mod` exists **and** its `go` directive is `1.24` or newer
  (parse the line `go 1.24` / `go 1.26` / etc.), use the **Go-tool
  path** (preferred).
- Otherwise, use the **project-local binary path**.

Do not guess. If `go.mod` exists but the Go version is below 1.24,
fall through to the binary path and tell the user why.

### 3a. Go-tool path (Go 1.24+ projects)

Propose the command, but **do not run it yet**:

```bash
go get -tool github.com/shatterproof-ai/refute/cmd/refute@<version>
```

Show the resulting `go.mod` diff to the user before writing. Generate
it by running `go get -tool ...@<version>` in a scratch copy, or by
describing the expected `tool` directive addition / update so the
user can see what will change. Wait for approval.

On approval:

1. Run the `go get -tool` command in the project root.
2. Verify with `go tool refute version` and show the output.
3. Stage `go.mod` (and `go.sum`) for the user to commit.

### 3b. Project-local binary path (non-Go or Go < 1.24)

Pick a directory based on what the project already uses:

- If `tools/` exists, use `tools/refute` and `tools/refute.version`.
- Else, use `.bin/refute` and `tools/refute.version` (create
  `tools/` for the version file).

Propose the changes before writing:

1. Create or update `tools/refute.version` containing the single line
   `<version>` (e.g., `v0.1.3`).
2. Download the matching release binary for the host platform from
   `https://github.com/shatterproof-ai/refute/releases/download/<version>/refute-<os>-<arch>`
   into the chosen directory and `chmod +x` it.

Show the diff for `tools/refute.version` (a one-line creation or
single-line change) before writing. Wait for approval.

On approval:

1. Write `tools/refute.version`.
2. Download the binary into `.bin/refute` or `tools/refute`.
3. Verify with `./.bin/refute version` (or `./tools/refute version`)
   and show the output.

Note in passing that the chosen directory should be in `.gitignore`
if the project does not want the binary checked in; the version file
**should** be committed either way so CI can resolve the pin.

### 4. Confirm and hand off

Print a one-line summary: which path was used, the pinned version,
and the verification output. Tell the user to commit the resulting
changes (`go.mod`/`go.sum`, or `tools/refute.version`).

## Out of scope

- Installing `refute` for the first time (covered by `install-refute`).
- Diagnosing a broken install (covered by `refute-doctor`).
- Bumping a pin across many repos in one pass.

## Refusals

- Floating tag (`@latest`, `@main`, branch names): refuse and ask for
  a release tag.
- Continuous-build / pre-release tag: warn and require an explicit
  override before proceeding; default is to refuse.
- Missing `go.mod` and no `tools/` or `.bin/` writable location: ask
  the user where to put the binary; do not guess.
