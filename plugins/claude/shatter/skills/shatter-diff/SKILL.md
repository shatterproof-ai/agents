---
name: shatter-diff
description: Run Shatter only on the functions changed between a base ref and the working tree. Maps git-diff hunks to function boundaries with Shatter's existing parsers and explores each changed function with the same primitive as a single-function run — for fast pre-commit and PR-CI feedback instead of re-exploring the whole repository.
---

## Model Guidance

Recommended model: low. The skill is procedural: resolve a base ref,
invoke `shatter diff` with the right flags, and report the per-function
results. No qualitative judgment is required beyond explaining failure
modes.

## Purpose

For downstream users of Shatter who want to explore *only what changed*.
A typical commit touches 2-4 functions, but a full `run-shatter` pass
re-explores every integrated target — often 80+ functions. `shatter diff`
narrows exploration to the functions that actually changed between a base
ref and the current working tree, so it is fast enough to run on every
commit or pull request.

This skill documents and drives the `shatter diff` command. It does not
reimplement git-diff parsing: the value of the command is that Shatter
itself maps diff hunks to functions using the *same* parsers and runs the
*same* function-level exploration primitive that a manual single-function
run uses. Skills and hooks that wrap Shatter for pre-commit should call
`shatter diff` rather than parsing `git diff` themselves.

## When to use

- **Pre-commit hook** — explore the functions a commit is about to
  introduce, before the commit lands. Use `--staged` so only staged
  changes are considered.
- **Pull-request CI** — explore everything changed since the branch
  diverged from the trunk: `shatter diff main`.
- **Reviewing a focused change** — you (or a reviewer) want Shatter's
  read on a specific set of edits without waiting for a full-repo run.

Use `run-shatter` instead when you want a full sweep of every integrated
target, or when there is no meaningful diff to scope to (for example, the
first run on a fresh checkout).

## Command

```
shatter diff [<base-ref>] [--staged] [--include-tests]
             [--output-dir <path>] [--format json|text] [--jobs <N>]
```

### Default behavior

- `shatter diff` with no base ref defaults to `HEAD~1`, i.e. it explores
  the functions changed by the **last commit** (`HEAD~1..` plus the
  working tree).
- `shatter diff HEAD~1` is the explicit form of the default: explore the
  last commit's changes.
- `shatter diff main` explores **all changes since the branch diverged
  from `main`** — every function touched on the current branch relative to
  the merge base with `main`. This is the form to use in PR CI.
- `shatter diff --staged` ignores commits and base refs and explores only
  the functions touched by **currently staged** changes (`git diff
  --cached`). This is the form to use in a pre-commit hook.

The base ref is resolved with git's normal ref rules, so tags, SHAs, and
`origin/main` all work. When both a base ref and `--staged` are given,
`--staged` wins and the base ref is ignored.

## How it works

1. **Read the diff.** `shatter diff` runs the equivalent of `git diff
   <base-ref>` (or `git diff --cached` under `--staged`) to get the set of
   changed files and their changed hunk line ranges.
2. **Map hunks to functions.** For each changed file in a supported
   language, Shatter parses the file with the **same function-boundary
   detection it already uses** for whole-file exploration and intersects
   each changed hunk's line range with the function boundaries. A function
   is selected when a changed hunk overlaps its body. This reuse is a hard
   requirement: `shatter diff` must not ship a separate diff-only parser,
   so the function identities it produces are identical to those a full
   run would report.
3. **Explore per function.** The mapped `<file>:<function>` targets are
   handed to the **same primitive used for single-function exploration**.
   Each changed function is explored independently, exactly as if it had
   been named on a single-function run.
4. **Aggregate.** Results for all explored functions are collected into
   one run directory and summary, in the same shape a standard run
   produces.

## Output

`shatter diff` writes the same artifacts as a standard Shatter run — per
function specs, reports, and a `summary.json` — into the output directory.

- Without `--output-dir`, results go to the default location a normal run
  uses (a timestamped `shatter-review/<timestamp>/`-style directory).
- With `--output-dir <path>`, results are written there instead.
- `--format text` (the default for terminal use) prints a human-readable
  per-function summary; `--format json` emits machine-readable JSON for CI
  steps and wrapping tools to consume.

Because the output format matches `run-shatter`, the `interpret-shatter-spec`
and `report-shatter-issues` skills work on a `shatter diff` run directory
without modification.

## Flags

- `--staged` — explore only staged changes (`git diff --cached`). Ignores
  any base ref. Intended for pre-commit hooks.
- `--include-tests` — also explore changed functions in test files. Off by
  default; changed test code is normally not worth exploring, but include
  it when the tests themselves carry logic you want covered.
- `--output-dir <path>` — write the run directory to `<path>` instead of
  the default location.
- `--format json|text` — output format. `text` for humans, `json` for CI
  and wrapper tooling.
- `--jobs <N>` — number of functions to explore concurrently. Tune to the
  CI runner's core count; higher values finish a multi-function diff
  faster at the cost of more parallel load.

## Pre-commit hook example

Wire `shatter diff --staged` into a pre-commit hook so each commit
explores only the functions it changes. Save as `.git/hooks/pre-commit`
(or add to an existing hook manager) and make it executable:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Explore only the functions in the staged change set.
# --format json lets the hook decide whether to block the commit.
out="$(mktemp -d)"
if ! shatter diff --staged --format json --output-dir "$out"; then
  echo "shatter diff failed to run; commit aborted." >&2
  echo "Run 'shatter diff --staged' manually to see the error." >&2
  exit 1
fi

# Inspect the summary if you want to gate the commit on findings.
# Here we only surface results and never block on exploration content;
# adjust to taste (e.g. fail when a changed function throws on every input).
echo "Shatter explored the staged changes — results in $out" >&2
exit 0
```

Notes for hook authors:

- Keep `--jobs` modest in a hook so a commit is not starved of CPU; the
  staged change set is usually small.
- A hook that finds **no changed functions** should let the commit proceed
  (see failure modes below) — an empty diff is not an error.
- Do the git-diff scoping with `shatter diff --staged`, not by parsing
  `git diff` in the hook. That is the whole point of the command: the hook
  stays a few lines and the function mapping matches what Shatter would
  report elsewhere.

## Failure modes

- **No functions found in the diff.** When the changed hunks do not
  overlap any function body — for example the diff only touches comments,
  imports, `README` files, or configuration — `shatter diff` explores
  nothing and exits successfully (exit 0) with an empty run and a clear
  "no changed functions to explore" message. Treat this as a no-op, not a
  failure; pre-commit hooks should allow the commit.
- **Invalid base ref.** If `<base-ref>` does not resolve to a commit
  (typo, missing branch, unfetched remote ref), the underlying `git diff`
  fails. `shatter diff` reports the git error (`unknown revision or path`)
  and exits non-zero without exploring anything. Fix the ref — fetch the
  remote, correct the name — and re-run.
- **Unparseable / unsupported changed file.** When a changed file is in a
  language Shatter cannot parse, or the parser cannot recover function
  boundaries for it, that file is **skipped with a warning** and the
  remaining changed files are still explored. The skip is reported so the
  gap is visible; it does not abort the whole run. If *every* changed file
  is unsupported, the result is the same as "no functions found" — an
  empty, successful run with a message explaining that no supported
  functions were in the diff.

## Out of scope

- Full-repository exploration (use `run-shatter`).
- Wiring a project-defined `shatter` wrapper into a target (use
  `add-shatter-target`).
- Diagnosing whether Shatter is installed and initialized (use
  `shatter-doctor`).
- Interpreting or reporting on the produced specs (use
  `interpret-shatter-spec` or `report-shatter-issues`).
