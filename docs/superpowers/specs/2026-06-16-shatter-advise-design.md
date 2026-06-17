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

Both skills share a discovery script and a common skill workflow. They differ
in which findings they present and which track they emphasize.

---

## Execution Model

The analysis work is split between a script and the agent:

**Script** (`catalog/skills/shatter-advise/scripts/discover_hotspots.py`):
Handles deterministic work that is testable without an LLM:
- detect languages from project markers
- find candidate files by static signals (path conventions, import patterns,
  grep-level structural patterns)
- load and parse Shatter run artifacts if `--run-dir` is provided
- proto-cluster candidates by static signals
- write a structured discovery JSON the agent reads to drive deep analysis

```
discover_hotspots.py
  --root <path>           project root to analyze (required)
  --run-dir <path>        optional prior run-shatter output directory
  --output <path>         where to write discovery.json (required)
```

Exit behavior:
- `0` on success
- `1` on input error (missing root, unreadable run-dir)

**Agent** (guided by SKILL.md):
Handles everything that requires reading and reasoning about code:
- read representative files from the script's shortlist
- apply taxonomy gates (constructibility, executability, coverage depth,
  measurement) — requires understanding code structure and semantics
- identify specific branch logic, plain-data contracts, shell/core boundaries
- assign confidence based on evidence quality
- write concrete cluster prescriptions
- produce findings, report.md, and findings.json

The SKILL.md files invoke the script, read its discovery output, then guide
the agent through deep analysis, cluster synthesis, and report generation.
Both `shatter-advise` and `shatter-gaps` follow this same flow; they differ
in which dispositions they include in their output.

The script is installed alongside the skill, following the same convention as
`run-shatter`'s `scripts/run_targets.py`.

---

## Inputs

Two analysis modes:

| Mode | Input |
|------|-------|
| Source-only | `--root` only |
| With artifacts | `--root` + `--run-dir` |

Source-only mode uses LLM-guided and static heuristic analysis over source
files. Where Refute's LSP backend would sharpen signal, findings are tagged
`IMPROVE-WITH-LSP` with the specific LSP fact that would help (see Confidence
Rules below).

When `--run-dir` is provided, the script parses:
- `summary.json` from the run-shatter output
- per-target `*.spec.json` files
- `unsupported` and `error_only` outcomes, which are merged into the hotspot
  list at elevated priority over source-only heuristic hotspots

---

## Analysis: Three Phases

### Phase 1 — Discovery

A broad structural read that detects candidate hotspot signals across the
project. The script looks for:

- **Handler files**: HTTP/GraphQL/MCP/CLI handlers, route files, RPC
  entrypoints (by path convention and import patterns)
- **Store/state files**: Zustand stores, Redux slices, global state modules
- **IO-heavy files**: files importing DB clients, HTTP clients, filesystem,
  subprocess, or env reads
- **Async-mixed files**: `async fn` / `async function` / `Promise` chains
  containing branching decision logic alongside `await` calls
- **Concurrency files**: goroutines, channels, timers, task spawns with
  embedded branch logic
- **Visibility signals**: exported functions delegating all decisions to
  unexported/private helpers; private helpers with significant branch logic
  unreachable as direct Shatter targets
- **Side-effect signals**: functions mixing module-level state mutation,
  logging, telemetry, or network writes with branching logic; high IO-line
  fraction in handlers
- **Generated/glue files**: `*.gen.*`, `*_generated.*`, resolver boilerplate

Discovery produces a raw hotspot list, not findings. No deep analysis happens
here.

### Phase 1.5 — Clustering

Before deep analysis, hotspots are grouped into clusters. The cluster key is:

```
pattern_id + tractability_gate + disposition + language + surface_type + failure_shape
```

Example `failure_shape` values:
- `handler_mixes_parse_auth_validate_db_render`
- `async_function_mixes_awaited_io_with_branch_logic`
- `store_action_captures_state_and_browser_globals`
- `external_decoder_hides_branch_driver`
- `generated_glue_contains_project_decisions`
- `opaque_resource_parameter_blocks_constructibility`

Artifact-backed hotspots (`unsupported`, `error_only` from spec JSONs) are
prioritized within clusters and as cluster representatives over source-only
heuristic hotspots.

For each cluster, up to 3 representative examples are selected for deep
analysis. Additional similar hotspots are listed without full sketches.

Default budget: **8 clusters × 3 examples = 24 deep analyses**. The report
states the budget explicitly:

```
Detected 87 hotspots.
Formed 11 clusters.
Deeply analyzed 8 clusters and 19 representative examples.
Listed 42 additional similar hotspots.
Skipped 26 low-priority hotspots due to budget.
```

### Phase 2 — Cluster Deep Analysis

For each selected cluster, the script reads the representative source files
and applies the taxonomy gates to the cluster as a whole:

1. **Constructibility** — can Shatter synthesize the inputs? Flags: opaque
   resources, uninferrable generic params, missing serde/deserialization
   derives, ownership shapes, unexported types.

2. **Executability** — will the function run after inputs are constructed?
   Flags: live-resource dependencies, precondition panics, missing
   validated-input boundaries, unsafe-to-repeat side effects.

3. **Coverage depth** — does useful branching live in instrumented project
   code? Flags: logic in callbacks, closures, factory returns, async `await`
   chains, external decoders, concurrency shells, and private helpers
   unreachable as direct targets.

4. **Measurement** — is the coverage denominator honest? Flags: high IO-line
   fractions, generated-code lines, functions whose primary purpose is side
   effects.

**Visibility** and **side effects** are cross-cutting signals evaluated
alongside the gates, not a fifth gate. Visibility primarily affects
constructibility and coverage depth. Side effects primarily affect
executability and measurement.

Each cluster analysis produces one concrete cluster-level recommendation (see
Prescription Standard below) and one or more findings. The cluster may produce
both a project finding and an engine finding when the same observation calls
for both a project refactor and a central Shatter fix. Those findings are
separate but linked.

---

## Dispositions

| Disposition | Meaning |
|-------------|---------|
| `PROJECT-FIX` | Target project should change shape |
| `ENGINE-GAP` | Shatter should fix this class centrally |
| `CONFIG-TUNE` | Current shape may be acceptable with better config |
| `JUSTIFIED-SKIP` | Exclusion is the honest result |

`shatter-advise` (`--mode advise`) emits `PROJECT-FIX`, `CONFIG-TUNE`, and
`JUSTIFIED-SKIP`. `shatter-gaps` (`--mode gaps`) emits `ENGINE-GAP`. The two
reports are never mixed, but findings may be linked across reports via
`linked_finding_ids`.

**Generated and framework glue** must be classified precisely:
1. Generated/framework code with no project decisions: `JUSTIFIED-SKIP`.
2. Generated/framework code containing project decisions: `PROJECT-FIX` to
   move decisions into hand-written helpers, then skip the generated shell.
3. Generated code inflating the coverage denominator: `JUSTIFIED-SKIP` or a
   denominator note under the measurement gate.

---

## Pattern Catalog

Named patterns map to stable `pattern_id` values:

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

The `async-shell-sync-core` pattern (from agents-arz):

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

```
finding_id            stable id for cross-references (e.g. pf-001, eg-001)
cluster_id            id of the parent cluster
pattern_id            stable taxonomy key
tractability_gate     constructibility | executability | coverage_depth | measurement
disposition           PROJECT-FIX | ENGINE-GAP | CONFIG-TUNE | JUSTIFIED-SKIP
confidence            low | medium | high (see rules below)
evidence:
  file                path relative to root
  symbol              function/type/module name
  line_range          [start, end] if known
  static_signal       what source pattern triggered this
  shatter_outcome     unsupported | error_only | low_coverage | none
  reason              plain-language explanation
suggested_refactor    concrete prescription (PROJECT-FIX only; v1 = manual sketch)
expected_coverage_gain  local | family | tier | corpus
effort_estimate       trivial | small | structural | adapter-sized
leverage_score        bucket derived from gain × inverse(effort) — see Leverage
manual_review_notes   semantic risks the implementing agent must preserve
engine_issue_ref      e.g. agents-2b3 (ENGINE-GAP findings only)
improve_with_lsp      specific LSP fact that would sharpen confidence, or null
linked_finding_ids    list of finding_ids in the other track sharing this evidence
```

---

## Confidence Rules

- **`high`**: Shatter artifact outcome (`unsupported` or `error_only`) plus
  matching source evidence confirm the finding.
- **`medium`**: Strong source evidence with clear symbol/file references, but
  no run artifact.
- **`low`**: Path/import/name-based signal only, likely pattern but not
  confirmed, or LSP required to verify.

`improve_with_lsp` names the specific LSP fact needed, not a generic caveat.
Examples:
- `exact symbol reachability from exported entry point`
- `private helper call graph from handler`
- `type ownership and Deserialize derive availability`
- `exported target discoverability`
- `rename/extract safety check`

---

## Leverage Scoring

Leverage is assigned by bucket, not by false numeric precision.

`expected_coverage_gain` scale:
- `local` — improves one function or small helper
- `family` — improves repeated functions of the same shape
- `tier` — improves a layer such as handlers, stores, or repositories
- `corpus` — improves many targets across the project or many projects

`effort_estimate` scale:
- `trivial` — rename, derive, config, small helper extraction
- `small` — one-file refactor with clear boundaries
- `structural` — repeated pattern across several files
- `adapter-sized` — requires fixtures, ports, harness setup, or tool adapter work

Leverage buckets:

| | trivial / small effort | structural effort | adapter-sized effort |
|-|----------------------|-------------------|---------------------|
| **corpus / tier gain** | highest | medium-high | medium |
| **family gain** | high | medium | lower |
| **local gain** | medium | lower | lowest |

If a numeric sort key is needed internally, render the human-readable bucket
in the report.

---

## Prescription Standard

Weak prescriptions ("split the handler") are not acceptable. Every
cluster-level `PROJECT-FIX` recommendation must answer:

1. What exact decision logic moves?
2. What new helper or core function should exist?
3. What plain-data input should it accept?
4. What plain-data result should it return?
5. What IO/framework/runtime code stays in the shell?
6. Which file/symbol should be migrated first?
7. What Shatter target should become more tractable afterward?
8. What semantic risks must a human or implementing agent preserve?

Example:

```
Cluster: handler-sandwich-split

Diagnosis:
  Several HTTP handlers combine request parsing, authorization, database reads,
  validation, response mapping, and telemetry in one function. Shatter can
  construct neither the framework state nor the database pool, and the branch
  drivers are not isolated as plain data.

Prescription:
  Introduce a pure decision helper for the repeated authorization and outcome
  classification shape:

    decideProjectUpdate(actor, projectSnapshot, input) -> UpdateProjectDecision

  The helper should accept only plain data:
    - actor role/account id
    - project ownership/status snapshot
    - normalized request input

  It should return a plain result/plan:
    - validation error
    - forbidden
    - no-op
    - update command
    - response classification

  Keep these in the handler shell:
    - framework extraction
    - database lookup/write
    - telemetry/logging
    - HTTP response rendering

  First migration target:
    handlers/projects.ts:updateProject — clearest repeated branch shape
    and highest IO-line fraction among the examples.

  Expected Shatter improvement:
    Shatter should explore validation, authorization, and outcome mapping
    without constructing HTTP framework state or a database.

  Manual review notes:
    Preserve authorization ordering. Do not change which errors are visible
    before authentication.
```

---

## Linked Project and Engine Findings

When one observation calls for both a project refactor and a Shatter engine
fix, emit one finding in each track and link them:

```
# Project report finding:
finding_id: pf-003
cluster_id: cluster-handler-sandwich-001
disposition: PROJECT-FIX
linked_finding_ids: [eg-001]

# Engine report finding:
finding_id: eg-001
cluster_id: cluster-handler-sandwich-001
disposition: ENGINE-GAP
engine_issue_ref: agents-2b3
linked_finding_ids: [pf-003]
```

The reports stay separate. The links make it clear both tracks came from the
same evidence.

---

## Architectural Ceiling Estimate

The report includes a qualitative architectural ceiling estimate that separates:

- branch-bearing project logic
- IO/framework shell lines
- generated glue
- external dependency internals
- unsupported engine-gap surfaces

Prefer ranges or qualitative buckets; avoid false numeric precision. Example:

```
Current architecture likely caps useful Shatter coverage at a medium level for
handler code because most handlers combine database effects with branch logic.
After extracting decision helpers for the top handler cluster, the
branch-bearing portion of those handlers should become high-tractability, while
the database shell remains a justified skip or scenario-fixture target.
```

If numbers are used, the report must explain the denominator.

---

## Output

Both skills produce outputs to the same directory structure:

```
shatter-review/advise-<timestamp>/
  report.md          human-readable markdown
  findings.json      machine-readable findings and clusters

shatter-review/gaps-<timestamp>/
  engine-gaps.md     human-readable markdown
  findings.json      machine-readable findings and clusters
```

### report.md (shatter-advise)

1. Executive summary — language(s), analysis mode, hotspot count, cluster
   count, finding counts by disposition, budget summary line
2. Cluster recommendations — ranked by leverage; each cluster includes:
   diagnosis, prescription (see standard above), representative examples,
   confidence, `IMPROVE-WITH-LSP` notes where applicable
3. Config-tune findings
4. Justified-skip register with rationale and generated-glue nuance
5. Architectural ceiling estimate

### engine-gaps.md (shatter-gaps)

1. Executive summary
2. ENGINE-GAP findings grouped by pattern class, each with `engine_issue_ref`
   where one exists and links to project-side clusters
3. Patterns with no open issue — candidates for new Shatter issues

### findings.json

Required fields for both skills:

```json
{
  "analyzer_version": "...",
  "input": {
    "root": "...",
    "mode": "advise|gaps|both",
    "run_dir": "...|null",
    "analysis_mode": "source_only|with_artifacts"
  },
  "budget": {
    "hotspots_detected": 0,
    "clusters_formed": 0,
    "clusters_analyzed": 0,
    "examples_analyzed": 0,
    "hotspots_listed": 0,
    "hotspots_skipped": 0
  },
  "clusters": [...],
  "findings": [...],
  "engine_finding_count": 0
}
```

For `shatter-advise`, `findings` contains PROJECT-FIX/CONFIG-TUNE/JUSTIFIED-SKIP.
For `shatter-gaps`, `findings` contains ENGINE-GAP. Clusters are included in
both so the link context is preserved.

### Console summary (both skills)

```
Analyzed <N> clusters across <M> hotspots.
  PROJECT-FIX: N  CONFIG-TUNE: N  JUSTIFIED-SKIP: N
  <N> engine-gap signal(s) detected — run shatter-gaps for the maintainer report.
Report: shatter-review/advise-<timestamp>/report.md
```

No offer to pipe into `report-shatter-issues` in v1. The new skills produce
standalone reports. Integration with `report-shatter-issues` is a separate
future design.

---

## Skill Relationships

| Skill | Relationship |
|-------|-------------|
| `run-shatter` | `shatter-advise` optionally consumes its run directory; chain them for richer signal |
| `report-shatter-issues` | Out of scope for v1; future integration requires expanding that skill's input schema |
| `refute-rename` | PROJECT-FIX sketches may suggest renames; defer apply to this skill |
| `refute` extract-function (agents-2b3) | PROJECT-FIX findings needing extract note the gap and provide a manual sketch |
| `shatter-gaps` | Same script with `--mode gaps`; emits ENGINE-GAP track only |

---

## Testing

Tests are split by what is testable at each layer.

### Script tests (`discover_hotspots.py`)

These are deterministic and do not require an LLM:

- script accepts `--root` without a run directory
- script accepts `--root` with a synthetic run-shatter directory
- artifact-backed `unsupported`/`error_only` outcomes appear in discovery
  output and are flagged as higher-priority than source-only heuristic hotspots
- handler-like files in a fixture produce handler-surface candidates
- generated files (`*.gen.go`, `*_generated.ts`) appear in the discovery
  output with `generated_glue` signal
- async-mixed files (containing `async fn` with branching) produce
  `async_mixed` signal
- discovery JSON is valid and parseable

### Skill acceptance checks

These verify agent behavior against synthetic fixtures and require running
the full skill:

- repeated handler-like files form one cluster, not N separate findings
- one observation produces linked project and engine findings with correct
  `linked_finding_ids`
- generated glue without project logic produces `JUSTIFIED-SKIP`
- generated glue with project logic produces `PROJECT-FIX`
- both `report.md` and `findings.json` are written to the output directory
- cluster prescriptions answer the required 8 questions (what moves, what
  contract, what stays, first target, expected improvement, semantic risks)

Fixture repos should be small synthetic directories with handler-like Go/TS
files and fake Shatter spec JSON artifacts. Real Shatter execution is not
required.

---

## Non-Goals (v1)

- Automated application of refactorings (blocked on agents-2b3).
- LSP-backed symbol analysis (noted as `IMPROVE-WITH-LSP`; deferred).
- Integration with `report-shatter-issues` (separate future design).
- Cross-project comparison or trend tracking.
- Modifying any target project files directly.
- Auditing Shatter engine correctness (that is `shatter-gaps`'s job).
