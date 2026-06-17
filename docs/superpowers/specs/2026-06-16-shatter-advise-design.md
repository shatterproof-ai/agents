# shatter-advise Design

## Overview

Two new skills in the `shatter` plugin that analyze a target project against
the Shatter tractability taxonomy and produce ranked recommendations:

- **`shatter-advise`** — project-facing; tells developers how to restructure
  their code so Shatter can explore it more thoroughly.
- **`shatter-gaps`** — maintainer-facing; surfaces ENGINE-GAP findings for
  Shatter contributors auditing what the engine should fix centrally.

The taxonomy spec driving both skills lives at
`docs/specs/2026-06-16-shatter-tractability-taxonomy.md`. The async-shell/sync-core
pattern from beads issue `agents-arz` is a first-class addition to that
catalog. The refute extract-function gap is tracked in `agents-2b3`.

---

## Inputs

Both skills accept the same inputs:

- **`--root <path>`** — target project root (defaults to current directory).
- **`--run-dir <path>`** — optional path to a prior `run-shatter` output
  directory (e.g. `shatter-review/<timestamp>/`). When provided, Shatter
  spec JSONs and run artifacts are merged in as higher-confidence signal.

Two analysis modes result:

| Mode | Input |
|------|-------|
| Source-only | project root only |
| With artifacts | project root + run directory |

Source-only mode uses LLM-based pattern recognition over source files.
Where Refute's LSP backend would improve signal quality, findings are tagged
`IMPROVE-WITH-LSP` rather than blocking analysis.

---

## Analysis: Two Phases

### Phase 1 — Discovery Pass

A cheap structural read that produces a prioritized hotspot list. The skill
looks for:

- **Handler files**: HTTP/GraphQL/MCP/CLI handlers, route files, RPC entrypoints
  (by path convention and import patterns)
- **Store/state files**: Zustand stores, Redux slices, global state modules
- **IO-heavy files**: files importing DB clients, HTTP clients, filesystem,
  subprocess, or env reads
- **Async-mixed files**: `async fn` / `async function` / `Promise` chains that
  contain branching decision logic alongside `await` calls — candidates for
  async-shell/sync-core split
- **Concurrency files**: goroutines, channels, timers, task spawns with embedded
  branch logic
- **Visibility signals**: exported functions that delegate all decisions to
  unexported/private helpers; private helpers with significant branch logic that
  Shatter cannot target directly
- **Side-effect signals**: functions mixing mutation of module-level state,
  logging, telemetry, or network writes with branching logic; high IO-line
  fraction in handlers
- **Generated/glue files**: `*.gen.*`, `*_generated.*`, resolver boilerplate —
  candidates for `JUSTIFIED-SKIP`

When a Shatter run directory is provided, `unsupported` and `error_only`
outcomes from spec JSONs are merged into the shortlist with elevated confidence.

Hotspots are ranked by probable tractability impact. Only hotspots in this
list proceed to Phase 2.

### Phase 2 — Deep Analysis

For each hotspot, the skill reads the relevant source and applies the taxonomy
gates:

1. **Constructibility** — can Shatter synthesize the inputs? Flags: opaque
   resources, uninferrable generic params, missing serde/deserialization
   derives, ownership shapes that block construction, unexported types.

2. **Executability** — will the function run after inputs are constructed?
   Flags: live-resource dependencies (`DATABASE_URL`, LSP subprocess, browser
   API), precondition panics, missing validated-input boundaries, unsafe-to-
   repeat side effects.

3. **Coverage depth** — does useful branching live in instrumented project code?
   Flags: logic in callbacks, closures, factory returns, async `await` chains,
   external decoders, concurrency shells, and private helpers unreachable as
   direct targets.

4. **Measurement** — is the coverage denominator honest? Flags: high IO-line
   fractions in handlers, generated-code lines that inflate the denominator,
   functions whose primary purpose is side effects.

**Visibility** and **side effects** are cross-cutting signals evaluated
alongside the gates rather than as a fifth gate. Visibility primarily affects
constructibility and coverage depth. Side effects primarily affect executability
and measurement.

Each finding is assigned a disposition:

| Disposition | Meaning |
|-------------|---------|
| `PROJECT-FIX` | Target project should change shape |
| `ENGINE-GAP` | Shatter should fix this class centrally |
| `CONFIG-TUNE` | Current shape may be acceptable with better config |
| `JUSTIFIED-SKIP` | Exclusion is the honest result |

`shatter-advise` reports PROJECT-FIX, CONFIG-TUNE, and JUSTIFIED-SKIP.
`shatter-gaps` reports ENGINE-GAP findings. The two sets are never mixed.

---

## Pattern Catalog

The following named patterns map to `pattern_id` values in findings:

| pattern_id | Summary |
|------------|---------|
| `functional-core-imperative-shell` | Extract decisions over plain data; keep IO in the shell |
| `handler-sandwich-split` | Parse / auth / validate / core / effect / render separation |
| `query-result-separation` | SQL in repo, rows mapped to plain snapshots, decisions in pure fns |
| `scenario-state-factories` | Deterministic factories for IO that must remain |
| `fixture-sets-external-boundary` | Project-owned fixtures for external decoder / FFI boundaries |
| `time-random-env-extraction` | Pass clock, ID generator, env values into the pure core |
| `browser-runtime-global-isolation` | Isolate `window`/`localStorage`/`fetch` in shell helpers |
| `factory-closure-capture` | Extract state transition helpers from stores/builders/registries |
| `callback-streaming-inversion` | Move chunk/event logic into plain-data functions |
| `concurrency-shell-extraction` | Extract planning functions; let concurrent shell apply them |
| `async-shell-sync-core` | Convert awaited inputs to plain data; extract sync decision core |
| `generated-framework-glue-avoidance` | Move decisions out of generated dispatch; skip generated code |
| `small-project-owned-ports` | Define minimal interfaces around opaque resources |
| `serialization-validated-input-boundary` | Explicit validation, structured errors, serialization derives |

The `async-shell-sync-core` pattern (from agents-arz) is first-class:

> Keep async code at the boundary for parse/load/effect/render operations.
> Convert awaited inputs into plain project-owned data before the core call.
> Extract deterministic decision logic into a synchronous helper.
> Return a result, plan, or command object from the sync helper.
> Let the async shell perform awaited effects after the core returns.
>
> Disposition is `PROJECT-FIX` when the sync core takes and returns ordinary
> data and avoids hidden IO, globals, or runtime handles. It is
> `JUSTIFIED-SKIP` when the behavior's essence is async: scheduling order,
> cancellation races, backpressure, or streaming protocol semantics.

---

## Finding Schema

Each finding carries:

```
pattern_id            stable taxonomy key (from table above)
tractability_gate     constructibility | executability | coverage_depth | measurement
disposition           PROJECT-FIX | ENGINE-GAP | CONFIG-TUNE | JUSTIFIED-SKIP
confidence            low | medium | high
evidence              file, symbol, reason string, or Shatter outcome
suggested_refactor    prose sketch + code snippet (PROJECT-FIX only; v1 = manual)
effort_estimate       trivial | small | structural | adapter-sized
leverage_score        rough impact ÷ effort (used for ranking)
engine_issue_ref      e.g. agents-2b3 for extract-function gap
improve_with_lsp      true | false (true = LSP analysis would sharpen confidence)
```

For PROJECT-FIX findings in v1, `suggested_refactor` contains a prose
description and a compact before/after code sketch. Automated apply requires
extract-function support in Refute (tracked in `agents-2b3`); until that
lands the skill generates sketches only.

Findings are ranked by `leverage_score` descending before output.

---

## Output

### shatter-advise

**Project report** (always produced):
`shatter-review/advise-<timestamp>/report.md`

Sections:
1. Executive summary — language(s), analysis mode, hotspot count, finding
   counts by disposition
2. Project-fix findings — ranked by leverage score; each with evidence,
   effort estimate, pattern sketch, visibility/side-effect notes, and
   `IMPROVE-WITH-LSP` tag where applicable
3. Config-tune findings — specific config recommendations
4. Justified-skip register — files/symbols recommended for exclusion with
   rationale
5. Architectural ceiling estimate — realistic coverage before refactoring,
   with denominator notes

**Console summary** (always):
- One line per hotspot: finding count + top disposition
- Total counts by disposition
- Path to project report
- Count of ENGINE-GAP signals observed (no detail): `N engine-gap signal(s)
  detected — run shatter-gaps for the maintainer report`
- Offer to pipe findings into `report-shatter-issues`

### shatter-gaps

**Engine gap report** (always produced when this skill is invoked):
`shatter-review/gaps-<timestamp>/engine-gaps.md`

Sections:
1. Executive summary
2. ENGINE-GAP findings grouped by pattern class, each with `engine_issue_ref`
   where one exists
3. Patterns with no open issue — candidates for new Shatter issues

**Console summary**: per-pattern counts, path to report, offer to pipe into
`report-shatter-issues`.

---

## Skill Relationships

| Skill | Relationship |
|-------|-------------|
| `run-shatter` | `shatter-advise` optionally consumes its run directory; chain them for richer signal |
| `report-shatter-issues` | Console summary offers to pipe findings; project report is structured for that skill |
| `refute-rename` | `shatter-advise` may recommend renames in a PROJECT-FIX sketch; defers apply to this skill |
| `refute` extract-function (agents-2b3) | PROJECT-FIX findings requiring extract note the gap and provide a manual sketch |
| `shatter-gaps` | Shares the same analysis engine; emits ENGINE-GAP track only |

---

## Non-Goals (v1)

- Automated application of refactorings (blocked on agents-2b3).
- LSP-backed symbol analysis (noted as `IMPROVE-WITH-LSP`; deferred).
- Cross-project comparison or trend tracking.
- Modifying any target project files directly.
- Auditing Shatter engine correctness (that is `shatter-gaps`'s job).
