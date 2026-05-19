---
name: wire-shatter-ci
description: Generate a GitHub Actions workflow that installs a pinned `shatter` binary, sets up the project's existing language toolchains, runs the integrated Shatter targets, and uploads the run directory as a workflow artifact. Detects current CI setup, drafts `.github/workflows/shatter.yml`, shows the diff, and writes on approval.
---

## Model Guidance

Recommended model: low. The skill is procedural: detect, draft, diff,
write, verify. No qualitative judgment required.

## Purpose

For downstream users of Shatter. Add a single GitHub Actions workflow
that runs `run-shatter` against the repository's integrated targets on
every push and pull request, and uploads the run directory as a workflow
artifact. Pin the `shatter` binary to a specific `BUILD=` tag so the
workflow is reproducible.

## Preconditions

### 1. At least one target must already be integrated

Run the discovery helper that ships with the `run-shatter` skill:

```bash
python3 scripts/run_targets.py --root . --json
```

If no target reports `"status": "integrated"`, stop and recommend the
user run `add-shatter-target` first. Do not write a workflow that would
have nothing to run.

### 2. The repository must use GitHub Actions

Confirm `.github/` exists (or that the user is willing to create it).
This skill is GitHub Actions only. Other CI systems are out of scope.

## Workflow

### 1. Detect existing CI configuration and toolchains

Inspect:

- `.github/workflows/*.yml` — is there already a `shatter.yml`? If so,
  stop and ask the user before overwriting.
- Existing workflows for Node version pins (`actions/setup-node` `with:
  node-version:`), Go version pins (`actions/setup-go` `with:
  go-version:`), and package manager (`pnpm/action-setup`, `yarn`,
  `bun`).
- Manifests in the repo for fallbacks:
  - `package.json` `"engines": {"node": ...}` or `"packageManager"`
    field
  - `go.mod` `go <version>` line
  - lockfiles: `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` /
    `bun.lockb`, `package-lock.json`

Pick the most specific value available. If nothing is found for a given
language but the repo has that language present (per
`run_targets.py` languages output), default to a current LTS or stable
release and note the default in the diff so the user can tighten it.

If the repo has no Node target and no Go target, set up only the
languages that are actually present.

### 2. Choose a pinned `BUILD=` tag

Default to the most recent known continuous build the user has been
using locally (ask if uncertain). The exact form passed to the install
script is documented by `install-shatter`:

```
BUILD=continuous-YYYYMMDD-HHMM-<sha>
```

Never use `latest` in the generated workflow — the issue spec requires
a pinned tag for repeatability.

### 3. Determine the run command

If the user has more than one integrated target, prefer the helper:

```bash
python3 scripts/run_targets.py --root . --json
```

For the workflow body, invoke the same helper the `run-shatter` skill
uses. If `run_targets.py` is vendored in the repo (e.g. under
`scripts/`), call it directly. Otherwise call each target's native
wrapper explicitly. Keep the run command surgical — one step that
exercises the integrated targets and writes artifacts under a known
directory such as `shatter-review/`.

### 4. Draft `.github/workflows/shatter.yml`

Use this template as a starting point. Replace the bracketed values
based on detection in step 1; remove setup steps for languages not
present in the repo.

```yaml
name: shatter

on:
  push:
    branches: [main]
  pull_request:

jobs:
  shatter:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '<detected-node-version>'

      - name: Set up pnpm
        uses: pnpm/action-setup@v4
        with:
          version: '<detected-pnpm-version>'

      - name: Install Node dependencies
        run: pnpm install --frozen-lockfile

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '<detected-go-version>'

      - name: Install shatter (pinned)
        env:
          BUILD: continuous-YYYYMMDD-HHMM-<sha>
          INSTALL_DIR: ${{ github.workspace }}/.shatter-bin
        run: |
          curl -sSL https://raw.githubusercontent.com/shatterproof-ai/shatter/main/install.sh | bash
          echo "${{ github.workspace }}/.shatter-bin" >> "$GITHUB_PATH"

      - name: Run Shatter
        run: python3 scripts/run_targets.py --root . --json

      - name: Upload Shatter run directory
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: shatter-run
          path: shatter-review/
          if-no-files-found: warn
```

Rules for the generated file:

- `BUILD:` must be a concrete pinned value, never `latest` and never
  unset.
- Include `actions/setup-node` only if Node is present; include
  `actions/setup-go` only if Go is present. Drop the pnpm step for
  npm/yarn/bun projects and replace with the matching install step.
- The upload step's `if: always()` keeps artifacts available even when
  Shatter exits non-zero on a failing target.
- The run step path (`shatter-review/`) should match what
  `run_targets.py` writes; if the user has customized the run
  directory, mirror that.

### 5. Show the diff before writing

Render a unified diff of the proposed new file and wait for approval.
If the user wants edits (different toolchain pin, different `BUILD=`,
different trigger branches), incorporate them before writing.

### 6. Write on approval

Create `.github/workflows/shatter.yml` with the approved content.
Preserve a trailing newline.

### 7. Verify

Re-read the file and confirm:

- `BUILD=` is set to a pinned tag (no `latest`, no empty value).
- `actions/upload-artifact` is present and points at the run directory.
- The integrated targets' run command is present.

Report a one-line summary: `wrote .github/workflows/shatter.yml
(BUILD=<tag>, targets=<n>)`.

## Out of scope

- Other CI systems (CircleCI, GitLab CI, Buildkite, etc.).
- Branch-protection rules or marking the new check as required.
- Posting Shatter results as PR comments.
- Authoring or modifying Shatter specs (covered by other skills).
- Adding `shatter` wrappers to projects (covered by
  `add-shatter-target`).

## Required companion

None bundled. The workflow this skill generates depends on the
`run_targets.py` helper that ships with the `run-shatter` skill;
the user's repo must have access to it (either vendored in
`scripts/` or invoked through the installed Shatter plugin cache).
