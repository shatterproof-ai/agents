---
name: run-shatter
description: Run all integrated Shatter targets in a repository, continue past per-target failures, capture reproducible review artifacts, and produce an analyst review explaining the most important observed behaviors in human terms.
---

## Model Guidance

Recommended model: high. The skill discovers targets and runs them
procedurally, but the review portion calls for qualitative case selection
and distinguishing program behavior from likely tool issues.

## Purpose

For downstream users of Shatter. Discover project-native `shatter`
wrappers, run each integrated target, save artifacts, then write a review
that explains the target's behavior in human terms and flags any tool
issues.

## Defaults

- Run every discovered supported-language target in the repository.
- A target is `integrated` only when it defines a local wrapper named
  `shatter` on a supported command surface.
- Targets without a local wrapper are reported as `not integrated`, never
  guessed at or auto-fixed.
- Use a dedicated run directory such as `shatter-review/<timestamp>/`.
- Report each failure as soon as it happens but keep running later
  integrated targets unless the user interrupts.

## Workflow

### 1. Run

```bash
python3 scripts/run_targets.py --root <repo> --json
```

If `run_targets.py` is not at `scripts/run_targets.py` relative to the
repo root, it ships alongside this skill in the Shatter plugin. Locate it
without hard-coding a version number:

```bash
find ~/.claude/plugins/cache -name run_targets.py -path '*/run-shatter/scripts/*' 2>/dev/null | head -1
```

The bundled helper:

- discovers supported-language targets (`Cargo.toml`, `go.mod`,
  `package.json`)
- marks each target as `integrated` or `not integrated`
- runs the target's native wrapper invocation for integrated targets
- keeps going after a failed target
- writes per-target artifacts and a final `summary.json`

Supported integration surfaces (v1):

- `package.json` with `scripts.shatter` — invoke via the package manager
  hinted by lockfile or `packageManager` field
- `Taskfile.yml` with a `shatter` task — invoke `task shatter` if
  available, else `npx task shatter`

For each integrated target run, preserve: the target root and detected
language set, the integration status and chosen surface, the exact native
invocation and working directory, stdout and stderr, per-target result
metadata including exit status, and the overall `summary.json`. If the
target's wrapper produces spec JSON, reports, or other exports, keep those
files alongside the captured console output.

### Recipe discovery and runs

A target may carry optional **recipes** — declarative documents that bind
each parameter of one function to its own provider (a live/seeded
resource, a registered stub, a pinned value, or default synthesis) so a
single run can combine, e.g., a real seeded database with an erroring
storage stub. Recipes are authored and validated by the
`compose-shatter-recipe` skill; this skill only **discovers and runs**
them.

For each discovered target with id `<target-id>`, enumerate its recipes:

```
.shatter/recipes/<target-id>/*.json
```

- A target with **no** matching directory, or no `*.json` files, simply
  has no recipes. Run it exactly as today (single bundled `State()`
  synthesis). Recipe discovery never fails on an absent recipe directory —
  the no-recipe path is unchanged and fully backward compatible.
- When recipes exist, run the target **once per recipe** in addition to
  (not instead of) the default run, so each forced branch family is
  explored. Label each run by recipe name (e.g.
  `sweeper.run_once / s3-delete-fails`) in the artifacts and review.
- A recipe is **validated before its run** (unknown parameter key,
  unregistered stub, stub/port-type mismatch, concrete-typed parameter,
  missing live scenario, unknown `schemaVersion`). A malformed recipe
  fails its own run with that precise error; report it as a recipe
  validation failure and **keep running** the other recipes and targets.
  Do not treat a recipe validation error as a target-program behavior.

See the `compose-shatter-recipe` skill for the recipe schema, stub/scenario
registration, and the full validation rules.

### 2. Review

Once the run completes, write a review of the captured artifacts with
these sections:

1. `Overall interpretation`
2. `Most important cases`
3. `Precise observed results`
4. `Possible issues or ambiguities`
5. `Recommended next step`

For the exact headings and per-section expectations, read
`references/report-schema.md`.

Prefer this evidence order:

1. spec JSON or other machine-readable artifacts
2. captured stdout and stderr from the run
3. generated reports or test exports

If exploration was partial for any target, say so explicitly.

### How to choose the most important cases

Prioritize 3-7 cases per integrated target that best explain the target's
behavior:

- thrown errors or failure paths
- broad input-domain splits
- boundary values
- surprising coercions, nullish handling, or edge cases
- cases that dominate the function's behavior
- signs that exploration is incomplete or unstable

### Case format

For each important case, include both:

- a human explanation of what the case means and why it matters
- precise evidence: representative inputs, exact outputs or errors, and
  any path condition or spec fragment available

Do not collapse the review into raw dumps. The human explanation is
required.

### Distinguish behavior from tool issues

Separate:

- normal target-program behavior
- uncertainty caused by partial exploration
- likely Shatter bugs or UX problems

Program exceptions discovered by Shatter are often useful findings, not
tool failures. Mark them as tool issues only when the evidence points to
Shatter itself: crashes, malformed output, inconsistent samples,
deserialization failures, impossible summaries, or missing artifacts.

## Handoff

End with a short summary that includes:

- one line per target with `succeeded`, `failed`, or `not integrated`
- immediate callouts for any failing targets
- overall counts for integrated, succeeded, failed, and not-integrated
  targets
- the run directory and key artifact paths
- the review itself, structured as above

Pass the run directory and the review to `report-shatter-issues` if the
user wants a markdown issue report.

## Required companion

- `scripts/run_targets.py` (bundled with this skill)
- `references/report-schema.md` (bundled with this skill;
  `report-shatter-issues` cross-references it as
  `../../run-shatter/references/report-schema.md`)
