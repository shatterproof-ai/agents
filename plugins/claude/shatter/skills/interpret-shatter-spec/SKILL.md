---
name: interpret-shatter-spec
description: Explain a single Shatter spec JSON file in human terms — a short paragraph of overall interpretation plus 2-4 representative cases. Use for a quick read of one function's exploration result, not a full run review.
---

## Model Guidance

Recommended model: low. Single-file parsing and a brief narrative; no
multi-section report assembly.

## Purpose

Take one Shatter spec JSON file (the exploration result for a single
function) and produce a short markdown summary that a human can read in
under a minute.

This skill is deliberately lighter than `run-shatter` or
`report-shatter-issues`. Stay in the "single spec, short summary" lane:

- one spec file in
- one short markdown summary out
- no whole-run reviews, no enumerated issue reports, no cross-spec
  comparisons

## Required input

A path to a spec JSON file (typically `shatter-artifacts/<name>.spec.json`)
or the spec contents on stdin. If the user gave neither, ask for one.

## Procedure

1. Read the spec JSON. If it fails to parse, say so and stop — do not
   invent content.
2. Identify the target function's name and signature if present.
3. Walk the recorded cases. For each, note:
   - the concrete inputs
   - the observed output, return value, or thrown error
   - the path condition or constraint that selected this case, if recorded
4. Group cases by behavior: normal returns, boundary values, thrown
   errors, and any obviously degenerate or tool-failure cases.
5. Pick 2-4 cases that best represent the function's behavior. Prefer:
   - one typical happy-path case
   - one boundary or edge case
   - one error or exception case, if any
   - one additional case only if it shows distinct behavior
6. Distinguish program behavior from likely Shatter tool issues
   (timeouts, unresolved symbols, empty exploration). Call tool issues
   out separately so the reader does not mistake them for program
   semantics.

## Output shape

Print markdown to stdout with this shape, and nothing else:

```
# <function name or spec file name>

<one short paragraph, roughly 100-200 words total across the whole
output, describing what the function appears to do, which inputs it
splits on, and any notable boundary or error behavior>

## Representative cases

- **<short label>** — inputs: `<concrete input>`; result: `<output or
  error>`
- **<short label>** — inputs: `<concrete input>`; result: `<output or
  error>`
- (2-4 bullets total)

## Ambiguities

- <one bullet per obvious ambiguity, or the single line "None observed.">
```

Keep the whole document tight. If the spec is small, lean toward 2
cases. If a section would be empty, write `None observed.` rather than
omitting the heading.

## Schema reference

The spec JSON is the per-function artifact produced by a Shatter run.
The full review and report schema lives in the `run-shatter` skill's
references at `catalog/skills/run-shatter/references/report-schema.md`
inside this repository; downstream installs may not ship that file, so
the relevant case fields are summarized here:

- `Case`: a short label for the behavior
- `Representative sample`: one concrete input and the resulting output
  or thrown error
- `Why it matters`: plain-language impact (optional in this skill's
  summary)

This skill uses only the case shape (label + input + result). It does
not produce the full `Overall interpretation` / `Most important cases`
/ `Precise observed results` / `Possible issues or ambiguities` /
`Recommended next step` structure — that belongs to `run-shatter`'s
review output and `report-shatter-issues`' markdown report.

## Out of scope

- Reviewing an entire Shatter run directory.
- Writing a durable markdown issue report (use `report-shatter-issues`).
- Comparing two spec files or diffing runs.
- Recommending fixes to the target program beyond noting ambiguities.
