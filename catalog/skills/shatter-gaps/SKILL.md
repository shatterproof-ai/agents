---
name: shatter-gaps
description: Analyze a project against the Shatter tractability taxonomy and produce an ENGINE-GAP report for Shatter maintainers — patterns where the engine should be fixed centrally rather than asking every project to reshape around them.
---

## Model Guidance

Recommended model: high. ENGINE-GAP findings require distinguishing a
project-specific code shape from a class of inputs the engine should handle
centrally — this is a judgment call that requires reading source carefully.

## Purpose

For Shatter maintainers and contributors. Identifies patterns where Shatter
itself should be fixed or extended, rather than asking the target project to
refactor. Produces an engine-gaps report separate from project recommendations.

Most users should run `shatter-advise` instead. This skill is for people
working on the Shatter engine.

## Required inputs

- Target project root (defaults to current directory; also accept `--root <path>`)
- Optional prior Shatter run directory (`--run-dir <path>`)

## Workflow

### 1. Collect inputs

Same as shatter-advise: accept `--root` and optional `--run-dir`.

### 2. Run discovery script

Same script as shatter-advise. Create a timestamped output directory:

```bash
OUTPUT_DIR="shatter-review/gaps-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUTPUT_DIR"
python3 <skill-dir>/../shatter-advise/scripts/discover_hotspots.py \
  --root <root> \
  --output "$OUTPUT_DIR/discovery.json" \
  [--run-dir <run-dir>]
```

### 3–5. Discovery, clustering, and deep analysis

Follow the same Phase 1, Phase 1.5, and Phase 2 process as shatter-advise
(same cluster selection, same taxonomy gates, same representative example
selection). The difference is what you look for during deep analysis:

For ENGINE-GAP findings, ask: "Is this a pattern the engine should handle
centrally, so no project needs to reshape around it?" Examples:

- **Constructibility**: Rust by-reference parameters, integer width/signedness
  loss, missing serde rename handling, field erosion during mutation, opaque
  types that are common enough to deserve a built-in generator.
- **Executability**: classes of setup failures Shatter could avoid by providing
  deterministic stubs for common resources (e.g. a test database URL injector).
- **Coverage depth**: unsupported dispatch forms (factory capture, closure
  return methods), missing generator support for common shapes.
- **Measurement**: Shatter counting lines in uninstrumented libraries, false
  "covered" lines from partial instrumentation.

When the same observation could be solved by either a project refactor OR an
engine fix, note both. Record the project-side fix as a linked finding with
`linked_finding_ids` pointing at what shatter-advise would recommend.

### 6. Write cluster engine prescriptions

For ENGINE-GAP clusters, the prescription must specify:
1. What exact input or execution class Shatter fails to handle?
2. Why this is the engine's responsibility rather than the project's?
3. What Shatter change would fix the class centrally?
4. How many projects or targets would benefit?
5. Does an open issue already track this? (`engine_issue_ref`)
6. What is the scope of the engine change (small fix, new generator, adapter)?

### 7. Write engine-gaps.md

Save to `$OUTPUT_DIR/engine-gaps.md`:

```markdown
# Shatter Engine Gap Report

**Root:** <root>
**Analysis mode:** source-only | with Shatter artifacts
**Date:** <date>

## Budget

(same budget line as shatter-advise)

## Engine Gap Findings

### Gap N: <pattern_id> — <failure_shape>

**Gate:** constructibility | executability | coverage_depth | measurement
**Disposition:** ENGINE-GAP
**Confidence:** high | medium | low
**engine_issue_ref:** <issue id or "none — candidate for new issue">

**What Shatter fails to handle:**
<specific input class or execution pattern>

**Why this is an engine responsibility:**
<why every project shouldn't need to reshape around this>

**Proposed engine fix:**
<what Shatter should do centrally>

**Estimated impact:**
<how many targets/projects would benefit>

**Linked project-side recommendation:**
<what shatter-advise would say; omit if no project-side angle>

---
(repeat)

## Patterns with no open issue

(ENGINE-GAP findings with no engine_issue_ref — candidates for filing)
```

### 8. Write findings.json

Same schema as shatter-advise findings.json, but `findings` contains only
ENGINE-GAP dispositions. Include `clusters` for cross-reference context.

### 9. Console summary

Print:
```
Analyzed N clusters across M hotspots.
  ENGINE-GAP: N
  N project-fix signal(s) detected — run shatter-advise for project recommendations.
Report: <path to engine-gaps.md>
```

## Out of scope

- PROJECT-FIX, CONFIG-TUNE, or JUSTIFIED-SKIP findings (use shatter-advise)
- Filing issues directly (note candidates for new issues; user files them)
- Modifying project files or Shatter source directly
