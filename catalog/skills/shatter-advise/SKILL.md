---
name: shatter-advise
description: Analyze a project's code structure against the Shatter tractability taxonomy and produce ranked cluster recommendations for improving Shatter coverage. Works from source alone or with a prior Shatter run directory for higher-confidence signal.
---

## Model Guidance

Recommended model: high. Phase 2 cluster analysis requires reading source
files and applying qualitative judgment about code structure, data flow, and
refactoring boundaries. Do not downgrade; the prescription quality depends on
careful reading.

## Purpose

For project teams who want Shatter to cover more of their codebase. Analyzes
the project against the Shatter tractability taxonomy (constructibility,
executability, coverage depth, measurement), groups findings into clusters by
repeated pattern, and produces actionable prescriptions for each cluster with
concrete helper boundaries and plain-data contracts.

This skill does not modify project code. It produces a report the team or an
implementing agent acts on.

## Required inputs

- Target project root (defaults to current directory; also accept
  `--root <path>`)
- Optional prior Shatter run directory (`--run-dir <path>`) for
  artifact-backed higher-confidence findings

## Workflow

### 1. Collect inputs

Ask the user for the project root and whether they have a prior Shatter run
directory. If `--root` and optionally `--run-dir` were passed as arguments,
use those directly.

### 2. Run discovery script

Locate the companion script at the same path as this skill file, under
`scripts/discover_hotspots.py`. Create a timestamped output directory:

The script lives alongside this skill file. Locate it by finding this SKILL.md file from the project's shatter-agents repo root; the script is at `catalog/skills/shatter-advise/scripts/discover_hotspots.py` relative to that root. Substitute the full path for `<skill-dir>`.

```bash
OUTPUT_DIR="shatter-review/advise-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUTPUT_DIR"
python3 <skill-dir>/scripts/discover_hotspots.py \
  --root <root> \
  --output "$OUTPUT_DIR/discovery.json" \
  [--run-dir <run-dir>]
```

If the script exits non-zero, report the error and stop.

### 3. Read discovery output

Read `discovery.json`. Note:
- `languages`: what languages the project uses
- `proto_clusters`: initial groupings by failure shape
- `candidates`: individual hotspot files with signals and priority
- `artifact_mode`: whether Shatter artifacts were loaded

If `candidates` is empty, write a brief `report.md` stating no tractability hotspots were detected, populate `findings.json` with zero-value budget fields, print the console summary with all zeros, and stop.

### 4. Select clusters and representative examples (Phase 1.5)

From the proto-clusters, select up to **8 clusters** to analyze deeply,
prioritizing:
1. Clusters with artifact-backed candidates first
2. Then clusters by candidate count and signal strength

For each cluster, select up to **3 representative examples** — prefer
artifact-backed files, then files with the most signals, then largest files.

Record the budget in the report header:
```
Detected N hotspots.
Formed N clusters.
Deeply analyzing N clusters and up to 3 examples each.
```

### 5. Deep analyze each cluster (Phase 2)

For each selected cluster, read the representative source files and apply
the four tractability gates:

**Constructibility**: Can Shatter synthesize the inputs?
Look for: opaque resources (`*sql.DB`, `AppState`, `PgPool`, browser APIs),
missing serialization derives, unexported types, generic params without
concrete bounds.

**Executability**: Will the function run after inputs are constructed?
Look for: live-resource dependencies (DATABASE_URL, HTTP servers, LSP
subprocess), precondition panics, functions that write to globals on every
call (unsafe to call repeatedly with generated inputs).

**Coverage depth**: Does useful branching live in instrumented code?
Look for: branch logic inside `await` chains, callbacks, unexported helpers,
external decoders, factory closures, concurrency goroutines.

**Measurement**: Is the coverage denominator honest?
Look for: handlers where most lines are IO statements (log, db.Exec,
w.WriteHeader), high side-effect line fraction, generated boilerplate
counted in the denominator.

**Cross-cutting signals** (not a fifth gate — apply alongside all four):
- *Visibility*: Is branch-bearing logic in an unexported/private function
  that Shatter cannot target directly? Does the exported surface expose it?
- *Side effects*: Does the function mutate global state, write to disk, or
  make network calls on every invocation?

Fold visibility and side-effect observations into the nearest gate's diagnosis — visibility belongs under coverage_depth, side effects belong under executability — or record them in `manual_review_notes` if they do not fit cleanly.

**Generated glue**: Classify carefully:
- Generated code with no project decisions → `JUSTIFIED-SKIP`
- Generated code containing project decisions → `PROJECT-FIX` (move logic
  to hand-written helper) plus a note to skip the generated shell
- Generated code inflating denominator → measurement note

For each cluster, assign:
- `pattern_id` from the catalog (see taxonomy spec)
- `tractability_gate` (primary gate being blocked)
- `disposition`: PROJECT-FIX, CONFIG-TUNE, or JUSTIFIED-SKIP
- `confidence`: high (artifact-backed + source), medium (source evidence,
  clear symbol refs), low (path/import heuristic only)

### 6. Write cluster prescriptions

For every PROJECT-FIX cluster, the prescription must answer all eight
questions:

Plain data means primitive types, structs/records of primitives, and enums — no database handles, no HTTP clients, no file descriptors, no closures.

1. What exact decision logic moves?
2. What new helper or core function should exist?
3. What plain-data input should it accept?
4. What plain-data result should it return?
5. What IO/framework/runtime code stays in the shell?
6. Which file/symbol should be migrated first?
7. What Shatter target should become more tractable afterward?
8. What semantic risks must a human or implementing agent preserve?

Include a compact before/after code sketch showing the key extraction.

If a finding also implies a Shatter engine gap (e.g. the project fix would
be easier with extract-function support in Refute), note it as a linked
engine finding with `engine_issue_ref` but do NOT include ENGINE-GAP detail
in this report. Just count it for the console summary.

### 7. Write report.md

Save to `$OUTPUT_DIR/report.md` with these sections:

```markdown
# Shatter Tractability Report

**Root:** <root>
**Analysis mode:** source-only | with Shatter artifacts
**Date:** <date>

## Budget

Detected N hotspots. Formed N clusters. Deeply analyzed N clusters
and N representative examples. Listed N additional similar hotspots.
Skipped N low-priority hotspots.

## Cluster Recommendations

### Cluster N: <pattern_id> — <failure_shape>

**Gate:** constructibility | executability | coverage_depth | measurement
**Disposition:** PROJECT-FIX | CONFIG-TUNE | JUSTIFIED-SKIP
**Confidence:** high | medium | low
**Leverage:** highest | high | medium | lower | lowest
**Effort:** trivial | small | structural | adapter-sized
**IMPROVE-WITH-LSP:** <specific LSP fact needed, or omit>

**Diagnosis:** <what is wrong and why Shatter cannot explore it>

**Prescription:**
<answer to all 8 questions above>

**Representative examples:**
- `<file>:<symbol>` — <one-line reason this is representative>

**Additional similar hotspots:** <list files not deeply analyzed>

**Manual review notes:** <semantic risks>

---
(repeat for each cluster)

## Config-Tune Findings

(findings where CONFIG-TUNE is the disposition)

## Justified-Skip Register

(files/symbols recommended for exclusion, with rationale)

## Architectural Ceiling Estimate

(qualitative estimate: what coverage is realistic before and after
the top cluster fixes; explain the denominator)
```

### 8. Write findings.json

Save to `$OUTPUT_DIR/findings.json`:
```json
{
  "analyzer_version": "1.0.0",
  "input": {
    "root": "<root>",
    "mode": "advise",
    "run_dir": "<run-dir or null>",
    "analysis_mode": "source_only | with_artifacts"
  },
  "budget": {
    "hotspots_detected": 0,
    "clusters_formed": 0,
    "clusters_analyzed": 0,
    "examples_analyzed": 0,
    "hotspots_listed": 0,
    "hotspots_skipped": 0
  },
  "clusters": [
    {
      "cluster_id": "cluster-001",
      "failure_shape": "...",
      "pattern_id": "...",
      "tractability_gate": "...",
      "disposition": "PROJECT-FIX",
      "confidence": "medium",
      "leverage": "high",
      "candidates": ["file1", "file2"]
    }
  ],
  "findings": [
    {
      "finding_id": "pf-001",
      "cluster_id": "cluster-001",
      "pattern_id": "...",
      "tractability_gate": "...",
      "disposition": "PROJECT-FIX",
      "confidence": "medium",
      "evidence": {
        "file": "...",
        "symbol": "...",
        "line_range": null,
        "static_signal": "...",
        "shatter_outcome": "unsupported | null",
        "reason": "..."
      },
      "suggested_refactor": "...",
      "expected_coverage_gain": "family",
      "effort_estimate": "small",
      "leverage": "high",
      "manual_review_notes": "...",
      "engine_issue_ref": null,
      "improve_with_lsp": null,
      "linked_finding_ids": []
    }
  ],
  "engine_finding_count": 0
}
```

### 9. Console summary

Print:
```
Analyzed N clusters across M hotspots.
  PROJECT-FIX: N  CONFIG-TUNE: N  JUSTIFIED-SKIP: N
  N engine-gap signal(s) detected — run shatter-gaps for the maintainer report.
Report: <path to report.md>
```

## Pattern catalog reference

The taxonomy spec at `docs/specs/2026-06-16-shatter-tractability-taxonomy.md`
(in the shatter-agents repo) defines all named patterns and their sketches.
The async-shell/sync-core pattern (agents-arz) is also first-class:

> Extract synchronous decision helpers from async functions. The helper
> accepts plain data converted from awaited inputs and returns a plain
> result/plan. The async shell handles awaits and effects before and after.
> Disposition is PROJECT-FIX when the core takes and returns ordinary data.
> JUSTIFIED-SKIP when behavior is inherently async (cancellation races,
> backpressure, streaming protocol semantics).

## Out of scope

- Automated application of refactorings (blocked on agents-2b3)
- LSP-backed symbol analysis (tag as IMPROVE-WITH-LSP with specific fact)
- ENGINE-GAP findings (use shatter-gaps for those)
- Modifying project files directly
