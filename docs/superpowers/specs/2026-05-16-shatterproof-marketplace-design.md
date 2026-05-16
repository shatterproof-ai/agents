---
name: shatterproof-marketplace-design
description: Design for turning shatter-agents into the shatterproof plugin marketplace with `shatter` and `refute` plugins, dual Claude Code + Codex packaging, canonical catalog sources, and committed generated plugin trees.
type: project
date: 2026-05-16
---

# Shatterproof Marketplace — Design

## 0. Context

`shatter-agents` today is a single-plugin Codex-format repository containing
three downstream-user skills: `run-shatter`, `review-shatter-output`,
`report-shatter-issues`. It also carries a repo-root `references/` directory,
two helper scripts (`run_targets.py`, `collect-context.sh`), a `tests/`
directory, and an initialized but empty Beads tracker.

This design turns the repo into the **shatterproof marketplace**: a plugin
marketplace that ships two plugins (`shatter`, `refute`) for both Claude Code
and OpenAI Codex, with canonical skill sources under `catalog/` and committed
generated plugin trees under `plugins/`.

The marketplace is single-owner and scoped to shatterproof tooling. It is
not a generic agent marketplace; future shatterproof tools may be added as
new plugins, but unrelated plugins are out of scope.

## 1. Repo identity and top-level layout

```
shatter-agents/
├── README.md                  # marketplace overview, install instructions
├── DESIGN.md                  # short pointer at conventions docs and this spec
├── AGENTS.md                  # agent-facing repo guide
├── CLAUDE.md                  # short, points at AGENTS.md
├── .beads/                    # tracker, already initialized
├── .claude-plugin/
│   └── marketplace.json       # generated; Claude Code marketplace manifest
├── catalog/                   # canonical sources — humans edit here
│   ├── plugin-versions.json   # { "<plugin>": { "version": "x.y.z", "content_hash": "..." } }
│   ├── plugins.json           # which catalog skills belong to which plugin; per-plugin metadata
│   └── skills/<skill-name>/
│       ├── SKILL.md           # shared body, includes `## Model Guidance` section
│       ├── metadata.json      # sidecar; copied verbatim into generated plugins
│       ├── CLAUDE.md          # optional Claude-only overlay (appended at build)
│       ├── CODEX.md           # optional Codex-only overlay (appended at build)
│       ├── references/        # optional companion files (copied verbatim)
│       └── scripts/           # optional companion files (copied verbatim)
├── plugins/                   # generated — committed for GitHub-source distribution
│   ├── claude/<plugin>/
│   │   ├── .claude-plugin/plugin.json
│   │   └── skills/<skill>/{SKILL.md,metadata.json,...}
│   └── codex/<plugin>/
│       ├── .codex-plugin/plugin.json
│       ├── assets/            # codex icon/screenshots
│       └── skills/<skill>/{SKILL.md,metadata.json,...}
├── scripts/
│   ├── build-plugins          # regenerates plugins/ and marketplace.json; auto-versions
│   └── check-plugins-clean    # CI: build to temp, diff against committed plugins/
├── tests/                     # pytest fixtures for skill load + build
└── docs/
    ├── installing-plugins.md
    ├── superpowers/specs/2026-05-16-shatterproof-marketplace-design.md  # this spec
    └── conventions/
        ├── overlays.md        # how CLAUDE.md/CODEX.md compose with SKILL.md
        ├── companion-files.md # references/ and scripts/ semantics
        └── versioning.md      # auto-versioning rules and content-hash inputs
```

Distribution requires `plugins/` to be committed: Claude Code's
`source: github` marketplace and the equivalent Codex install path fetch
raw repository files with no build step. Drift is prevented by CI rather
than by removing the committed tree.

DESIGN.md stays short — under one screen — and links to the conventions
docs and this spec. Bento's approach of blending marketplace structure,
worktree policy, customization conventions, and model-guidance rationale
into one DESIGN.md is rejected: those concerns have different lifecycles.

## 2. Build pipeline

`scripts/build-plugins`, in order, from a clean state:

1. **Load catalog.** Read `catalog/plugins.json` (plugin → skill list and
   per-plugin metadata), `catalog/plugin-versions.json` (current versions and
   content hashes), and walk `catalog/skills/`.
2. **Validate sources.** For each skill: SKILL.md frontmatter contains
   `name` and `description` and no other keys (the contract is intentionally
   minimal; repo-local metadata goes in `metadata.json`); `metadata.json`
   parses; companion paths exist; overlay files (if present) start with a
   level-2 heading and do not contain frontmatter.
3. **Wipe and regenerate `plugins/`.** Delete `plugins/claude/` and
   `plugins/codex/` entirely, then recreate from sources. Wiping prevents
   stale-file accumulation, which is the most common source of drift in
   bento-style generated-but-committed layouts.
4. **For each plugin × target (claude, codex):**
   - Compose `SKILL.md` = canonical body, then append the target-specific
     overlay (CLAUDE.md or CODEX.md) if present, separated by a horizontal
     rule. Overlays append content inside the body; they never mutate
     frontmatter.
   - Copy `metadata.json`, `references/`, `scripts/` verbatim into
     `plugins/<target>/<plugin>/skills/<skill>/`.
   - Write the target-appropriate `plugin.json` (Claude vs Codex schema)
     with name, description, version (computed below), author, and any
     Codex `interface` block declared in `catalog/plugins.json`.
   - For Codex, copy `assets/` (icon/screenshots) from
     `catalog/plugins/<plugin>/codex-assets/` if present.
5. **Auto-version.** Compute a content hash over each plugin's generated
   tree (sorted file paths + per-file SHA-256 + manifest fields excluding
   the version itself). If the hash differs from the value recorded in
   `catalog/plugin-versions.json`, bump the patch version and update the
   hash atomically; otherwise no-op. Write the resolved version into the
   generated manifests. The build is idempotent: running it twice in a row
   produces no diff on the second run.
6. **Write `.claude-plugin/marketplace.json`** listing one entry per plugin
   from `catalog/plugins.json`, each pointing at `./plugins/claude/<name>`.

`scripts/check-plugins-clean`:
- Runs `build-plugins` to a temp directory.
- `diff -r` against committed `plugins/`, `.claude-plugin/marketplace.json`,
  and `catalog/plugin-versions.json`.
- Exit nonzero on any difference. Wired into a GitHub Actions check on
  pushes to `main` and on PRs (no PRs are opened by this repo's workflow,
  but the check still gates merges done locally before push).

**Versioning discipline.**

- Patch versions are auto-bumped by the builder when content changes; no
  human action required.
- Major and minor versions are manual: a contributor edits
  `catalog/plugin-versions.json` directly. The builder accepts any version
  greater than or equal to its auto-bump target and leaves the field alone;
  it warns on downgrade.
- Bento's `bump-plugin-versions` script is not adopted.

## 3. Initial plugin and skill content

**`catalog/plugins.json`** (illustrative):

```json
{
  "plugins": {
    "shatter": {
      "description": "Install, run, and review Shatter; draft markdown issue reports.",
      "skills": ["install-shatter", "run-shatter", "report-shatter-issues"],
      "claude": { "author": "Shatterproof AI" },
      "codex": {
        "interface": {
          "displayName": "Shatter",
          "category": "Developer Tools",
          "capabilities": ["Interactive", "Write"],
          "brandColor": "#2C6E49"
        }
      }
    },
    "refute": {
      "description": "Install Refute and diagnose its setup for symbol-aware refactoring.",
      "skills": ["install-refute", "refute-doctor"],
      "claude": { "author": "Shatterproof AI" },
      "codex": {
        "interface": {
          "displayName": "Refute",
          "category": "Developer Tools",
          "capabilities": ["Interactive", "Write"],
          "brandColor": "#2C6E49"
        }
      }
    }
  }
}
```

**Migrations during the bootstrap:**

| From | To | Note |
|---|---|---|
| `skills/run-shatter/SKILL.md` | `catalog/skills/run-shatter/SKILL.md` | body expanded to subsume the review (see below) |
| `scripts/run_targets.py` | `catalog/skills/run-shatter/scripts/run_targets.py` | ships with the plugin |
| `skills/review-shatter-output/SKILL.md` | merged into `run-shatter`, then deleted | no longer a standalone skill |
| `skills/report-shatter-issues/SKILL.md` | `catalog/skills/report-shatter-issues/SKILL.md` | unchanged in scope |
| `scripts/collect-context.sh` | `catalog/skills/report-shatter-issues/scripts/collect-context.sh` | ships with the plugin |
| `references/report-schema.md` | `catalog/skills/run-shatter/references/report-schema.md` | `report-shatter-issues` cross-references it via the relative path `../../run-shatter/references/report-schema.md` (both skills ship in the same `shatter` plugin, so the path is stable in generated output) |
| `.codex-plugin/plugin.json` (root) | deleted | superseded by generated per-plugin manifests |
| `.claude/settings.local.json` | retained | local agent settings, not packaging |

**Merged `run-shatter` scope.** The combined skill performs end-to-end
exploration: discover targets, run integrated wrappers (continuing past
per-target failures), capture artifacts, then produce the analyst review
with the existing five sections — `Overall interpretation`, `Most important
cases`, `Precise observed results`, `Possible issues or ambiguities`,
`Recommended next step`. `report-shatter-issues` consumes that review as
its input.

**`install-shatter` (new).** Detects platform, installs the `shatter`
binary via the published install script (continuous build, pinned BUILD tag
for CI, or build-from-source), verifies with `shatter --help`, runs
`shatter init` in the current project root, and writes a guarded usage
stanza into the target project's primary agent doc (see Usage-stanza
contract below). Beads `agents-gre` covers this skill and stays open until
v1 lands.

**`install-refute` (new).** Detects target language(s) from `go.mod`,
`Cargo.toml`, `package.json`; picks the install path (Go-tool dependency
for Go 1.24+, `go install` for personal shell use, build-from-source as
fallback); installs the matching backends (`gopls`, `rust-analyzer`,
`typescript-language-server`); verifies with `refute version`; writes the
guarded usage stanza into the target project's primary agent doc; points
the user at `refute-doctor` for the next step.

**`refute-doctor` (new).** Runs `refute doctor` and parses its output; for
each language relevant to the project, reports backend status with the
exact remediation command; summarizes which refactoring operations are
currently usable.

**Usage-stanza contract** (used by both `install-shatter` and
`install-refute`):

- Pick order: `AGENTS.md` if it exists, else `CLAUDE.md`, else create
  `docs/<tool>-usage.md` and add a one-liner in `README.md` pointing at it.
- Stanza is bracketed by HTML-comment markers:
  `<!-- shatter:usage -->` / `<!-- /shatter:usage -->` (and similarly for
  refute). Re-running the install skill replaces the stanza in place; it
  does not duplicate.
- Stanza content names the installed binary version, the backends installed
  (for refute), and the relevant skills to invoke next.

**Model hints** (each skill carries a `## Model Guidance` section in the
body plus the same value in `metadata.json` under `recommended_model`):

| Skill | Recommended model |
|---|---|
| `install-shatter` | low |
| `run-shatter` | high |
| `report-shatter-issues` | mid |
| `install-refute` | low |
| `refute-doctor` | mid |

`recommended_model` lives in `metadata.json`, not in SKILL.md frontmatter.
Reasoning, documented in `docs/conventions/overlays.md`:

1. **Semantic non-portability.** The three-bucket `low|mid|high` mapping
   is Claude-shaped (Haiku/Sonnet/Opus). Codex, Gemini, and local-model
   runtimes do not share that three-tier hierarchy.
2. **Schema non-portability.** SKILL.md frontmatter is the typed contract;
   unknown keys happen to work today but are not part of any spec.
3. **Temporal non-portability.** "High" today means Opus 4.7; the bucket
   label has no version pin and ages worse than the body prose.

The `## Model Guidance` body section is the human-facing form and survives
cross-marketplace copy. `metadata.json` is the machine-readable form for
any future discovery tool.

## 4. Tests and CI

`tests/` at the repo root, pytest-based:

- `test_build_idempotent.py` — `build-plugins` produces zero diff on a
  second run into the same temp directory.
- `test_skills_load.py` — for each skill in `catalog/skills/`: SKILL.md has
  parseable frontmatter with `name` and `description`; `metadata.json`
  parses; companion scripts are executable; any companion path referenced
  in the body exists.
- `test_overlay_composition.py` — for each skill with an overlay, the
  composed Claude or Codex SKILL.md contains both the base body and the
  overlay content, in that order, with no duplicated frontmatter.
- `test_marketplace_manifest.py` — `marketplace.json` lists exactly the
  plugins in `catalog/plugins.json`, each with a `source` pointing at an
  existing `plugins/claude/<name>/` directory.
- `test_run_targets.py` — the existing test, retargeted at the new
  location of `run_targets.py` under `catalog/skills/run-shatter/scripts/`.
- `test_install_skills_update_docs.py` — fixture projects exercising the
  pick order (AGENTS.md present, CLAUDE.md only, neither); assert the
  guarded stanza ends up in the right file with markers, and that
  re-running replaces in place.

GitHub Actions (`.github/workflows/ci.yml`):

```yaml
jobs:
  build-clean:
    steps:
      - checkout
      - setup-python
      - run: scripts/check-plugins-clean
  tests:
    steps:
      - checkout
      - setup-python
      - run: python -m pytest tests/
```

`check-plugins-clean` is the non-bypassable gate that prevents committed
generated output from drifting away from canonical sources. Combined with
the auto-versioning step in §2, every catalog change ships with a
consistent generated tree and an appropriate version bump.

## 5. What was kept and what was changed from bento

**Kept:**

- Canonical-source / generated-output split (`catalog/` → `plugins/`).
- Platform overlays (`CLAUDE.md`, `CODEX.md`) appended to a shared SKILL.md
  at build time.
- Stable marketplace.json format for Claude Code's `source: github` install.

**Rejected or changed:**

- Bento's ~27 KB build script is replaced by a wipe-and-regenerate builder
  (target: 200-400 lines of Python). In-place reconciliation is the source
  of bento's complexity and we avoid it.
- Bento has no consistency gate. `check-plugins-clean` is mandatory here.
- Bento bundles a wide "everything" plugin that re-includes the narrow
  plugins' skills, flooding skill discovery. We ship only narrow plugins.
- Bento's `bump-plugin-versions` script is replaced by auto-versioning
  inside the builder, keyed on a content hash.
- Bento puts `recommended_model: low|mid|high` in SKILL.md frontmatter.
  We move it to `metadata.json` and document the portability reasons.
- Bento mixes multiple conventions (worktree root, agent-plugins
  customization, model guidance, hook format) into a single DESIGN.md.
  We keep DESIGN.md short and split conventions into per-topic files.
- The `agent-plugins/` user-customization convention is not adopted in v1.
  None of the initial five skills need user-editable templates. It can be
  adopted later when a skill actually needs it.

## 6. Deferred work (Beads issues)

| ID | Skill | Plugin | Notes |
|---|---|---|---|
| `agents-gre` | install-shatter | shatter | **Pulled into v1**, issue stays open until v1 merges. |
| `agents-4tm` | add-shatter-target | shatter | Deferred. |
| `agents-4z3` | interpret-shatter-spec | shatter | Deferred. |
| `agents-16f` | wire-shatter-ci | shatter | Deferred; blocked by `agents-4tm`. |
| `agents-fqc` | shatter-doctor | shatter | Deferred; blocked by `agents-gre`. Agent-driven; not reliant on a `shatter doctor` subcommand. |
| `agents-smh` | refute-rename | refute | Deferred. |
| `agents-ya6` | refute-from-plan | refute | Triage; blocked by `agents-smh` until plan-file format is settled. |
| `agents-b33` | pin-refute | refute | Deferred. |

## 7. Out of scope for this design

- Generic agent-marketplace use (other vendors' plugins).
- A wide everything-plugin that re-bundles narrow plugins.
- The `agent-plugins/` user-customization convention.
- Hooks at the marketplace level (no v1 skill needs a hook).
- Slash-command custom registrations on Codex (Codex does not support them
  for skill plugins today; users invoke skills by name).
- Other CI systems (CircleCI, GitLab CI, Buildkite) for `wire-shatter-ci`
  when that skill is eventually built.
- Java, Kotlin, or Python backends for `refute-doctor` (not claimed for
  refute v0.1).

## 8. Acceptance for "v1 lands"

- `catalog/` contains the five v1 skills with SKILL.md + metadata.json.
- `scripts/build-plugins` and `scripts/check-plugins-clean` exist; both
  pass clean on the committed tree.
- `plugins/claude/shatter/`, `plugins/codex/shatter/`,
  `plugins/claude/refute/`, `plugins/codex/refute/` are present and
  byte-for-byte equal to what the builder produces.
- `.claude-plugin/marketplace.json` lists both plugins.
- `tests/` passes on `python -m pytest tests/`.
- `.github/workflows/ci.yml` runs `check-plugins-clean` and tests.
- README, DESIGN.md, AGENTS.md, CLAUDE.md, and the conventions docs are
  written.
- Beads `agents-gre` is closed with the merge SHA after landing.
