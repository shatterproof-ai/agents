---
name: shatter-doctor
description: Diagnose a project's Shatter setup without running exploration or modifying anything — verify the `shatter` binary, parse `.shatter/config.yaml`, and report each discovered target's integration status with a recommended next step.
---

## Model Guidance

Recommended model: mid. Procedural diagnostic with light judgment on
which target verdicts matter and which remediation skill to recommend.

## Purpose

For downstream users of Shatter. Tell the user whether Shatter is
installed, whether the project is initialized, and which discovered
targets are wired up — without running any Shatter exploration and
without modifying the project.

## Required inputs

- The path to the project root (defaults to the current working
  directory).

## Hard constraints

- Diagnose only. Do not run `shatter` on any target.
- Do not create, edit, or initialize files in the project.
- If `.shatter/config.yaml` is missing, report it and stop — do not call
  `shatter init`.

## Behavior

### 1. Check the `shatter` binary

Run:

```bash
shatter --version
```

Capture stdout. If the command is missing or non-zero, point the user at
the `install-shatter` skill and continue with the remaining checks (they
are still useful even when the binary is missing).

If a version string is captured, parse the continuous-build tag from it
(format `continuous-YYYYMMDD-HHMM-<sha>`). Best-effort, compare against
the published manifest:

```bash
curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter/main/dist/manifest.json
```

If the fetch succeeds and exposes a current build tag, compare:

- exact match → report `matches published manifest`
- installed tag older than published → report `stale: published is <tag>`
- installed tag newer or unrelated → report `ahead of or unrelated to
  published manifest`

If the fetch fails (offline, 404, non-JSON), report the version without
a manifest comparison and note `manifest check skipped`. Do not fail the
diagnosis on a missing manifest.

### 2. Check `.shatter/config.yaml`

If the file is missing, record `missing` and point the user at
`install-shatter` (which runs `shatter init`).

If the file exists, parse it as YAML:

```bash
python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" .shatter/config.yaml
```

- If parsing succeeds, report `parsed OK`.
- If parsing fails, capture the error message and any line number from
  the parser output and report `parse error at line N: <message>`.

If `pyyaml` is unavailable, fall back to a syntax sanity check by
reading the file and reporting `parse skipped: pyyaml not installed,
file is N bytes`. Do not invent schema errors.

### 3. Discover targets and their integration status

Use the bundled discovery function from the `run-shatter` skill without
executing any target:

```bash
python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "catalog/skills/run-shatter/scripts")
from run_targets import discover_integrated_targets
print(json.dumps(discover_integrated_targets(Path(".").resolve()), indent=2))
PY
```

If the skill catalog is not co-located with the project, adjust the
`sys.path.insert` to point at the installed plugin location (look under
`~/.claude/plugins/.../catalog/skills/run-shatter/scripts` or wherever
the `shatter` plugin is installed). Do not invoke `run_targets.py`
directly with `--json` — that helper *runs* every integrated target,
which violates the diagnose-only constraint of this skill.

The discovery output is a list of target dicts with these fields:

- `root` — relative target path
- `languages` — `["go"]`, `["rust"]`, `["typescript"]`, or a union
- `status` — `integrated` or `not_integrated`
- `surface` — `{type, path}` for integrated targets, else `null`
- `reason` — short proximate reason for the verdict
- `wrapper_command` — the project-defined invocation, if any

### 4. Print the report

Render in this shape. Use a compact table for the targets section so the
verdicts line up.

```
## Shatter Health

- Binary: shatter <version> (<continuous tag>; <manifest verdict>)
  OR  Binary: MISSING — run install-shatter
- Config: .shatter/config.yaml parsed OK
  OR  Config: .shatter/config.yaml parse error at line N: <message>
  OR  Config: .shatter/config.yaml missing — run install-shatter

### Targets

| Path | Language | Integrated | Surface | Reason |
|------|----------|------------|---------|--------|
| .    | go       | yes        | Taskfile.yml (task shatter) | local Taskfile task |
| web  | typescript | no       | —       | no local shatter wrapper command |

### Recommended next steps

- For each `not_integrated` target: run the `add-shatter-target` skill
  against `<path>`.
- If the binary is missing or stale: run the `install-shatter` skill.
- If `.shatter/config.yaml` is missing: run the `install-shatter` skill.
- If everything is green: run the `run-shatter` skill to exercise the
  integrated targets.
```

End the report with a one-line summary, one of:

- `Shatter is ready for all discovered targets.`
- `Shatter is blocked: <N> binary/config issue(s), <M> not-integrated
  target(s) — see above.`

## Out of scope

- Installing or upgrading the binary (covered by `install-shatter`).
- Wiring a project-defined `shatter` wrapper into a target (covered by
  `add-shatter-target`).
- Running Shatter on any target (covered by `run-shatter`).
- Filing issues for tool problems (covered by `report-shatter-issues`).

## Required companion

- `catalog/skills/run-shatter/scripts/run_targets.py` — imported as a
  module for its `discover_integrated_targets` function. This skill
  ships no scripts of its own; the discovery logic lives with
  `run-shatter` so target detection stays consistent across skills.
