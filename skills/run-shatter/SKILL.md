---
name: run-shatter
description: Run all integrated Shatter targets in a repository, continue past per-target failures, and capture reproducible review artifacts plus summaries for downstream analysis. Use when a downstream user wants broad project-native Shatter execution rather than an ad hoc one-off command.
---

## Purpose

This skill is for downstream users of Shatter, not maintainers of the Shatter repo.

Use it to discover project-native `shatter` wrappers, run each integrated target,
and save enough context for later review.

## Defaults

- By default, run every discovered supported-language target in the repository.
- A target is `integrated` only when it defines a local wrapper command named
  `shatter` on a supported command surface.
- Targets without a local wrapper must be reported as `not integrated`, not
  guessed or auto-fixed.
- Create a dedicated run directory such as `shatter-review/<timestamp>/`.
- Report each failure as soon as it happens, but continue with later integrated
  targets unless the user interrupts you.

## Default workflow

Run the helper first:

```bash
python3 ../../scripts/run_targets.py --root <repo> --json
```

The helper should:

- discover supported-language targets (`Cargo.toml`, `go.mod`, `package.json`)
- mark each target as `integrated` or `not integrated`
- run the target's native wrapper invocation for integrated targets
- keep going after a failed target
- write per-target artifacts and a final `summary.json`

## Supported integration surfaces

In v1, treat these local wrapper surfaces as integrated:

- `package.json` with `scripts.shatter`
- `Taskfile.yml` with a `shatter` task

Use the native invocation for the surface:

- package scripts: `npm run shatter`, `pnpm run shatter`, `yarn shatter`, or
  `bun run shatter`, based on package manager hints
- Taskfile: `task shatter` when available, otherwise `npx task shatter`

## Capture requirements

For every integrated target run, preserve:

- the target root and detected language set
- the integration status and chosen surface
- the exact native invocation and working directory
- stdout and stderr
- per-target result metadata including exit status
- the overall `summary.json`

If the target's wrapper produces spec JSON, reports, or other exports, keep
those files alongside the captured console output.

## Handoff

End with a short summary that includes:

- one line per target with `succeeded`, `failed`, or `not integrated`
- immediate callouts for any failing targets
- overall counts for integrated, succeeded, failed, and not-integrated targets
- the run directory and key artifact paths

Pass the per-target artifacts for the interesting targets to
`review-shatter-output` and `report-shatter-issues`.
