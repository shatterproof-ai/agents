# Shatterproof Marketplace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `shatter-agents` into the shatterproof plugin marketplace with two committed plugins (`shatter`, `refute`) for both Claude Code and OpenAI Codex, built deterministically from canonical sources under `catalog/`.

**Architecture:** Canonical sources live under `catalog/skills/<name>/`. A single Python builder (`scripts/build-plugins`) wipes and regenerates `plugins/claude/` and `plugins/codex/`, composes platform overlays, copies companion files, auto-bumps patch versions via a content hash, and writes `.claude-plugin/marketplace.json`. A second script (`scripts/check-plugins-clean`) re-runs the build into a temp dir and diffs against the committed output; CI enforces no drift.

**Tech Stack:** Python 3 (stdlib only for the builder; pytest for tests), bash for one existing companion script, GitHub Actions for CI, Beads for tracking.

---

## File Structure

**Created during this plan:**

```
shatter-agents/
├── README.md
├── DESIGN.md
├── AGENTS.md
├── CLAUDE.md
├── .github/workflows/ci.yml
├── .gitignore                                    # add .codex and pytest cache
├── .claude-plugin/marketplace.json                # generated
├── catalog/
│   ├── plugins.json
│   ├── plugin-versions.json
│   └── skills/
│       ├── install-shatter/{SKILL.md, metadata.json, scripts/update_usage_stanza.py}
│       ├── run-shatter/{SKILL.md, metadata.json, scripts/run_targets.py, references/report-schema.md}
│       ├── report-shatter-issues/{SKILL.md, metadata.json, scripts/collect-context.sh}
│       ├── install-refute/{SKILL.md, metadata.json, scripts/update_usage_stanza.py}
│       └── refute-doctor/{SKILL.md, metadata.json}
├── plugins/
│   ├── claude/{shatter,refute}/...               # generated
│   └── codex/{shatter,refute}/...                # generated
├── scripts/
│   ├── build-plugins                              # new, replaces scripts/run_targets.py at this path
│   └── check-plugins-clean                        # new
├── tests/
│   ├── test_build_idempotent.py
│   ├── test_skills_load.py
│   ├── test_overlay_composition.py
│   ├── test_marketplace_manifest.py
│   ├── test_install_skills_update_docs.py
│   ├── test_run_targets.py                        # existing, path updated
│   └── fixtures/                                  # existing
└── docs/
    ├── installing-plugins.md
    ├── conventions/{overlays.md, companion-files.md, versioning.md}
    └── superpowers/{specs,plans}/                 # exist
```

**Deleted during this plan:**

- `skills/run-shatter/`, `skills/review-shatter-output/`, `skills/report-shatter-issues/`, then empty `skills/`
- `references/report-schema.md`, then empty `references/`
- `scripts/run_targets.py`, `scripts/collect-context.sh` (moved into skills)
- `.codex-plugin/plugin.json`, then empty `.codex-plugin/`

---

## Phase A — Catalog scaffolding and builder

### Task 1: Catalog scaffolding

**Files:**
- Create: `catalog/plugins.json`
- Create: `catalog/plugin-versions.json`
- Create: `catalog/skills/.gitkeep` (so empty dir survives the first commit)
- Modify: `.gitignore` (add `.codex`, `__pycache__/`, `.pytest_cache/`, `/plugins/_build/` for builder temp output)

- [ ] **Step 1: Create `catalog/plugins.json`**

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
          "brandColor": "#2C6E49",
          "shortDescription": "Run Shatter on a project and produce an analyst review."
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
          "brandColor": "#2C6E49",
          "shortDescription": "Install and diagnose Refute for CLI-driven refactors."
        }
      }
    }
  }
}
```

- [ ] **Step 2: Create `catalog/plugin-versions.json`** (initial; builder will manage from here on)

```json
{
  "shatter": { "version": "0.1.0", "content_hash": "" },
  "refute":  { "version": "0.1.0", "content_hash": "" }
}
```

- [ ] **Step 3: Create `catalog/skills/.gitkeep`** (empty file)

- [ ] **Step 4: Append to `.gitignore`**

```
.codex
__pycache__/
*.pyc
.pytest_cache/
/plugins/_build/
```

- [ ] **Step 5: Commit**

```bash
git add catalog/ .gitignore
git commit -m "scaffold catalog/ and gitignore additions"
```

---

### Task 2: Builder — module skeleton and constants

**Files:**
- Create: `scripts/build-plugins` (executable, shebang `#!/usr/bin/env python3`)
- Create: `tests/test_build_plugins.py` (new — tests for the builder itself, distinct from the per-test-file suites in later tasks)

- [ ] **Step 1: Write the skeleton with constants and a no-op `main`**

```python
#!/usr/bin/env python3
"""Build shatterproof marketplace plugins from catalog sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = REPO_ROOT / "catalog"
SKILLS_DIR = CATALOG_DIR / "skills"
PLUGINS_DIR = REPO_ROOT / "plugins"
PLUGINS_JSON = CATALOG_DIR / "plugins.json"
VERSIONS_JSON = CATALOG_DIR / "plugin-versions.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
TARGETS = ("claude", "codex")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class BuildError(Exception):
    """Raised when validation or build fails."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build shatterproof plugins.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to build into (default: this repo). Used by check-plugins-clean.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate sources and report what would change; do not write.",
    )
    args = parser.parse_args(argv)
    # Subsequent tasks fill this in.
    print("build-plugins: skeleton ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make executable:

```bash
chmod +x scripts/build-plugins
```

- [ ] **Step 2: Write the first test — script imports and main returns 0**

`tests/test_build_plugins.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build-plugins"


def _load_build_module():
    spec = importlib.util.spec_from_loader(
        "build_plugins",
        importlib.machinery.SourceFileLoader("build_plugins", str(SCRIPT_PATH)),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_main_returns_zero():
    build = _load_build_module()
    assert build.main([]) == 0
```

- [ ] **Step 3: Run the test, expect PASS**

```bash
python -m pytest tests/test_build_plugins.py -v
```

Expected: `test_main_returns_zero PASSED`.

- [ ] **Step 4: Commit**

```bash
git add scripts/build-plugins tests/test_build_plugins.py
git commit -m "add build-plugins skeleton with smoke test"
```

---

### Task 3: Builder — catalog loader and frontmatter parser

**Files:**
- Modify: `scripts/build-plugins` (add `load_catalog`, `parse_frontmatter`, dataclasses)
- Modify: `tests/test_build_plugins.py` (add loader tests with temp catalog)

- [ ] **Step 1: Write failing tests for loader**

Add to `tests/test_build_plugins.py`:

```python
import json
from pathlib import Path
import pytest


def _make_catalog(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog"
    (catalog / "skills" / "hello").mkdir(parents=True)
    (catalog / "skills" / "hello" / "SKILL.md").write_text(
        "---\nname: hello\ndescription: Greet the world.\n---\n\nHi.\n",
        encoding="utf-8",
    )
    (catalog / "skills" / "hello" / "metadata.json").write_text(
        '{"recommended_model": "low"}\n', encoding="utf-8"
    )
    (catalog / "plugins.json").write_text(json.dumps({
        "plugins": {
            "greetings": {
                "description": "Greet things.",
                "skills": ["hello"],
                "claude": {"author": "X"},
                "codex": {"interface": {"displayName": "Greetings"}},
            }
        }
    }), encoding="utf-8")
    (catalog / "plugin-versions.json").write_text(
        '{"greetings": {"version": "0.1.0", "content_hash": ""}}\n',
        encoding="utf-8",
    )
    return catalog


def test_load_catalog_returns_plugins_and_skills(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    loaded = build.load_catalog(catalog)
    assert list(loaded.plugins) == ["greetings"]
    assert loaded.plugins["greetings"].skills == ["hello"]
    assert "hello" in loaded.skills
    assert loaded.skills["hello"].frontmatter["name"] == "hello"
    assert loaded.skills["hello"].metadata == {"recommended_model": "low"}


def test_parse_frontmatter_rejects_extra_keys():
    build = _load_build_module()
    bad = "---\nname: x\ndescription: y\nrecommended_model: low\n---\n\nbody\n"
    with pytest.raises(build.BuildError, match="extra frontmatter key"):
        build.parse_frontmatter(bad, source="x/SKILL.md")
```

- [ ] **Step 2: Run tests, confirm both fail with `AttributeError`**

```bash
python -m pytest tests/test_build_plugins.py::test_load_catalog_returns_plugins_and_skills tests/test_build_plugins.py::test_parse_frontmatter_rejects_extra_keys -v
```

Expected: `AttributeError: module 'build_plugins' has no attribute 'load_catalog'`.

- [ ] **Step 3: Implement `parse_frontmatter`, dataclasses, and `load_catalog` in `scripts/build-plugins`**

Insert below the constants (before `main`):

```python
from dataclasses import dataclass, field

ALLOWED_FRONTMATTER_KEYS = frozenset({"name", "description"})


@dataclass
class Skill:
    name: str
    source_dir: Path
    frontmatter: dict[str, str]
    body: str
    metadata: dict
    overlays: dict[str, str] = field(default_factory=dict)   # {"claude": "...", "codex": "..."}
    references: list[Path] = field(default_factory=list)
    scripts: list[Path] = field(default_factory=list)


@dataclass
class PluginSpec:
    name: str
    description: str
    skills: list[str]
    claude: dict
    codex: dict


@dataclass
class Catalog:
    plugins: dict[str, PluginSpec]
    skills: dict[str, Skill]
    versions: dict[str, dict]


def parse_frontmatter(text: str, source: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise BuildError(f"{source}: missing or malformed frontmatter")
    raw, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise BuildError(f"{source}: malformed frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    for required in ("name", "description"):
        if required not in fm:
            raise BuildError(f"{source}: frontmatter missing required key {required!r}")
    extra = set(fm) - ALLOWED_FRONTMATTER_KEYS
    if extra:
        raise BuildError(f"{source}: extra frontmatter key(s) {sorted(extra)} not allowed")
    return fm, body


def _collect_companion_files(skill_dir: Path, sub: str) -> list[Path]:
    d = skill_dir / sub
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file())


def load_skill(skill_dir: Path) -> Skill:
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise BuildError(f"{skill_dir}: missing SKILL.md")
    fm, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"), str(skill_md))
    if fm["name"] != name:
        raise BuildError(
            f"{skill_md}: frontmatter name {fm['name']!r} does not match directory {name!r}"
        )
    metadata_path = skill_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    overlays: dict[str, str] = {}
    for overlay_name, key in (("CLAUDE.md", "claude"), ("CODEX.md", "codex")):
        op = skill_dir / overlay_name
        if op.is_file():
            text = op.read_text(encoding="utf-8")
            if text.startswith("---"):
                raise BuildError(f"{op}: overlays must not contain frontmatter")
            if not text.lstrip().startswith("## "):
                raise BuildError(f"{op}: overlays must start with a level-2 heading")
            overlays[key] = text
    return Skill(
        name=name,
        source_dir=skill_dir,
        frontmatter=fm,
        body=body,
        metadata=metadata,
        overlays=overlays,
        references=_collect_companion_files(skill_dir, "references"),
        scripts=_collect_companion_files(skill_dir, "scripts"),
    )


def load_catalog(catalog_dir: Path) -> Catalog:
    plugins_data = json.loads((catalog_dir / "plugins.json").read_text(encoding="utf-8"))
    versions = json.loads((catalog_dir / "plugin-versions.json").read_text(encoding="utf-8"))
    plugins: dict[str, PluginSpec] = {}
    skills: dict[str, Skill] = {}
    for name, p in plugins_data["plugins"].items():
        plugins[name] = PluginSpec(
            name=name,
            description=p["description"],
            skills=list(p["skills"]),
            claude=dict(p.get("claude", {})),
            codex=dict(p.get("codex", {})),
        )
        for skill_name in p["skills"]:
            if skill_name in skills:
                continue
            skill_dir = catalog_dir / "skills" / skill_name
            skills[skill_name] = load_skill(skill_dir)
    # Cross-check: every plugin's skills exist on disk
    for plugin in plugins.values():
        for s in plugin.skills:
            if s not in skills:
                raise BuildError(f"plugin {plugin.name}: skill {s!r} not found in catalog/skills/")
    return Catalog(plugins=plugins, skills=skills, versions=versions)
```

- [ ] **Step 4: Run tests, confirm PASS**

```bash
python -m pytest tests/test_build_plugins.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build-plugins tests/test_build_plugins.py
git commit -m "build-plugins: catalog loader and frontmatter parser"
```

---

### Task 4: Builder — skill composition and companion copy

**Files:**
- Modify: `scripts/build-plugins` (add `compose_skill`, `write_skill`)
- Modify: `tests/test_build_plugins.py`

- [ ] **Step 1: Failing tests for composition**

Add to `tests/test_build_plugins.py`:

```python
def test_compose_skill_appends_overlay(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    (catalog / "skills" / "hello" / "CLAUDE.md").write_text(
        "## Claude-only\nspecific\n", encoding="utf-8"
    )
    cat = build.load_catalog(catalog)
    composed = build.compose_skill(cat.skills["hello"], "claude")
    assert composed.startswith("---\nname: hello\ndescription: Greet the world.\n---\n")
    assert "## Claude-only\nspecific" in composed
    assert composed.index("Hi.") < composed.index("## Claude-only")


def test_compose_skill_no_overlay_returns_base(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    cat = build.load_catalog(catalog)
    composed = build.compose_skill(cat.skills["hello"], "codex")
    assert composed.endswith("Hi.\n") or composed.endswith("Hi.")
    assert "## " not in composed.split("---\n", 2)[-1].split("\n", 1)[0]


def test_write_skill_copies_companions(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    (catalog / "skills" / "hello" / "scripts").mkdir()
    helper = catalog / "skills" / "hello" / "scripts" / "say.sh"
    helper.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    helper.chmod(0o755)
    cat = build.load_catalog(catalog)
    out = tmp_path / "out"
    build.write_skill(cat.skills["hello"], "claude", out / "skills" / "hello")
    assert (out / "skills" / "hello" / "SKILL.md").is_file()
    assert (out / "skills" / "hello" / "metadata.json").is_file()
    copied = out / "skills" / "hello" / "scripts" / "say.sh"
    assert copied.is_file()
    assert copied.stat().st_mode & 0o111  # exec bits preserved
```

- [ ] **Step 2: Run tests, confirm FAIL** (`compose_skill`, `write_skill` undefined).

- [ ] **Step 3: Implement `compose_skill` and `write_skill`**

Add to `scripts/build-plugins` after `load_catalog`:

```python
def compose_skill(skill: Skill, target: str) -> str:
    fm_lines = [f"{k}: {v}" for k, v in skill.frontmatter.items()]
    parts = ["---"]
    parts.extend(fm_lines)
    parts.append("---")
    parts.append(skill.body.rstrip("\n"))
    overlay = skill.overlays.get(target)
    if overlay:
        parts.append("\n---\n")
        parts.append(overlay.rstrip("\n"))
    return "\n".join(parts) + "\n"


def _copy_with_mode(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    src_mode = src.stat().st_mode
    if src_mode & stat.S_IXUSR:
        dst.chmod(dst.stat().st_mode | 0o111)


def write_skill(skill: Skill, target: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SKILL.md").write_text(compose_skill(skill, target), encoding="utf-8")
    (out_dir / "metadata.json").write_text(
        json.dumps(skill.metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for sub in ("references", "scripts"):
        src_root = skill.source_dir / sub
        if not src_root.is_dir():
            continue
        for src in src_root.rglob("*"):
            if src.is_file():
                rel = src.relative_to(skill.source_dir)
                _copy_with_mode(src, out_dir / rel)
```

- [ ] **Step 4: Run tests, confirm PASS**

```bash
python -m pytest tests/test_build_plugins.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build-plugins tests/test_build_plugins.py
git commit -m "build-plugins: skill composition and companion copy"
```

---

### Task 5: Builder — plugin manifests, content hash, auto-versioning

**Files:**
- Modify: `scripts/build-plugins` (add `compute_plugin_hash`, `bump_version_if_changed`, `write_plugin_manifests`)
- Modify: `tests/test_build_plugins.py`

- [ ] **Step 1: Failing tests for hashing and version bump**

Add to `tests/test_build_plugins.py`:

```python
def test_compute_plugin_hash_is_deterministic(tmp_path):
    build = _load_build_module()
    a = tmp_path / "a" ; b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "skill.md").write_text("body\n", encoding="utf-8")
        (d / "extra.json").write_text("{}\n", encoding="utf-8")
    assert build.compute_plugin_hash(a) == build.compute_plugin_hash(b)


def test_compute_plugin_hash_changes_on_content_change(tmp_path):
    build = _load_build_module()
    d = tmp_path / "p" ; d.mkdir()
    (d / "f.txt").write_text("one", encoding="utf-8")
    first = build.compute_plugin_hash(d)
    (d / "f.txt").write_text("two", encoding="utf-8")
    assert build.compute_plugin_hash(d) != first


def test_bump_version_if_changed_bumps_patch_on_hash_mismatch():
    build = _load_build_module()
    versions = {"shatter": {"version": "1.2.3", "content_hash": "old"}}
    bumped = build.bump_version_if_changed(versions, "shatter", "new")
    assert bumped == "1.2.4"
    assert versions["shatter"] == {"version": "1.2.4", "content_hash": "new"}


def test_bump_version_if_changed_noop_when_hash_matches():
    build = _load_build_module()
    versions = {"shatter": {"version": "1.2.3", "content_hash": "same"}}
    bumped = build.bump_version_if_changed(versions, "shatter", "same")
    assert bumped == "1.2.3"
    assert versions["shatter"]["version"] == "1.2.3"


def test_bump_version_keeps_version_when_patch_is_zero():
    """Patch=0 is the manual-bump anchor. First build after a manual
    major/minor bump keeps the version and only updates the hash."""
    build = _load_build_module()
    versions = {"shatter": {"version": "2.0.0", "content_hash": "old"}}
    bumped = build.bump_version_if_changed(versions, "shatter", "new")
    assert bumped == "2.0.0"
    assert versions["shatter"]["content_hash"] == "new"


def test_bump_version_initial_empty_hash_keeps_initial_version():
    """A fresh plugin-versions.json entry (empty hash, patch=0) does not
    bump on the very first build; it just records the hash."""
    build = _load_build_module()
    versions = {"shatter": {"version": "0.1.0", "content_hash": ""}}
    bumped = build.bump_version_if_changed(versions, "shatter", "first")
    assert bumped == "0.1.0"
    assert versions["shatter"]["content_hash"] == "first"


def test_write_plugin_manifests_writes_claude_and_codex(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    cat = build.load_catalog(catalog)
    out = tmp_path / "out"
    (out / "claude" / "greetings").mkdir(parents=True)
    (out / "codex" / "greetings").mkdir(parents=True)
    build.write_plugin_manifests(cat.plugins["greetings"], "9.9.9", out)
    claude = json.loads((out / "claude" / "greetings" / ".claude-plugin" / "plugin.json").read_text())
    codex  = json.loads((out / "codex"  / "greetings" / ".codex-plugin"  / "plugin.json").read_text())
    assert claude["version"] == "9.9.9"
    assert claude["author"] == {"name": "X"}
    assert codex["version"] == "9.9.9"
    assert codex["interface"]["displayName"] == "Greetings"
```

- [ ] **Step 2: Run tests, confirm FAIL.**

- [ ] **Step 3: Implement**

Add to `scripts/build-plugins`:

```python
def compute_plugin_hash(plugin_dir: Path) -> str:
    h = hashlib.sha256()
    files = sorted(p for p in plugin_dir.rglob("*") if p.is_file())
    for f in files:
        rel = f.relative_to(plugin_dir).as_posix().encode("utf-8")
        h.update(rel + b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def bump_version_if_changed(versions: dict, plugin: str, new_hash: str) -> str:
    """If the plugin's content hash changed, bump patch (unless patch is 0,
    which is the manual-bump anchor — see docs/conventions/versioning.md)."""
    entry = versions.setdefault(plugin, {"version": "0.1.0", "content_hash": ""})
    old_version = entry["version"]
    if entry["content_hash"] == new_hash:
        return old_version
    major, minor, patch = (int(x) for x in old_version.split("."))
    if patch == 0:
        new_version = old_version
    else:
        new_version = f"{major}.{minor}.{patch + 1}"
    entry["version"] = new_version
    entry["content_hash"] = new_hash
    return new_version


def write_plugin_manifests(plugin: PluginSpec, version: str, out_root: Path) -> None:
    claude_dir = out_root / "claude" / plugin.name / ".claude-plugin"
    codex_dir  = out_root / "codex"  / plugin.name / ".codex-plugin"
    claude_dir.mkdir(parents=True, exist_ok=True)
    codex_dir.mkdir(parents=True, exist_ok=True)
    claude_author = plugin.claude.get("author", "Shatterproof AI")
    claude_manifest = {
        "name": plugin.name,
        "description": plugin.description,
        "version": version,
        "author": {"name": claude_author} if isinstance(claude_author, str) else claude_author,
        "skills": "./skills/",
    }
    codex_manifest = {
        "name": plugin.name,
        "description": plugin.description,
        "version": version,
        "author": claude_manifest["author"],
        "skills": "./skills/",
        "interface": plugin.codex.get("interface", {}),
    }
    (claude_dir / "plugin.json").write_text(json.dumps(claude_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (codex_dir  / "plugin.json").write_text(json.dumps(codex_manifest,  indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run tests, confirm PASS.**

```bash
python -m pytest tests/test_build_plugins.py -v
```

Expected: 13 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build-plugins tests/test_build_plugins.py
git commit -m "build-plugins: content hash, auto-version, manifests"
```

---

### Task 6: Builder — marketplace.json + end-to-end `build_all`

**Files:**
- Modify: `scripts/build-plugins` (add `write_marketplace_manifest`, `build_all`, wire `main`)
- Modify: `tests/test_build_plugins.py`

- [ ] **Step 1: Failing test for end-to-end build**

Add:

```python
def test_build_all_end_to_end(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    out = tmp_path / "repo"
    out.mkdir()
    (out / "catalog").symlink_to(catalog)
    build.build_all(out)
    assert (out / "plugins" / "claude" / "greetings" / "skills" / "hello" / "SKILL.md").is_file()
    assert (out / "plugins" / "codex"  / "greetings" / "skills" / "hello" / "SKILL.md").is_file()
    mp = json.loads((out / ".claude-plugin" / "marketplace.json").read_text())
    assert mp["plugins"][0]["name"] == "greetings"
    assert mp["plugins"][0]["source"] == "./plugins/claude/greetings"
    versions = json.loads((catalog / "plugin-versions.json").read_text())
    assert versions["greetings"]["version"] == "0.1.0"   # patch=0 anchor; first build records hash, no bump
    assert versions["greetings"]["content_hash"] != ""


def test_build_all_is_idempotent(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    out = tmp_path / "repo"
    out.mkdir()
    (out / "catalog").symlink_to(catalog)
    build.build_all(out)
    snap1 = sorted(p.relative_to(out).as_posix() for p in (out / "plugins").rglob("*") if p.is_file())
    hash1 = json.loads((catalog / "plugin-versions.json").read_text())["greetings"]["content_hash"]
    build.build_all(out)
    snap2 = sorted(p.relative_to(out).as_posix() for p in (out / "plugins").rglob("*") if p.is_file())
    hash2 = json.loads((catalog / "plugin-versions.json").read_text())["greetings"]["content_hash"]
    assert snap1 == snap2
    assert hash1 == hash2
```

- [ ] **Step 2: Run tests, confirm FAIL.**

- [ ] **Step 3: Implement `write_marketplace_manifest` and `build_all`**

Add to `scripts/build-plugins`:

```python
def write_marketplace_manifest(catalog: Catalog, out_root: Path) -> None:
    plugins_list = []
    for name in catalog.plugins:
        plugins_list.append({
            "name": name,
            "description": catalog.plugins[name].description,
            "version": catalog.versions[name]["version"],
            "source": f"./plugins/claude/{name}",
            "author": catalog.plugins[name].claude.get("author", "Shatterproof AI"),
        })
    payload = {
        "name": "shatterproof",
        "owner": {"name": "Shatterproof AI"},
        "metadata": {"description": "Plugins for Shatter and Refute."},
        "plugins": plugins_list,
    }
    out = out_root / ".claude-plugin" / "marketplace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_all(output_root: Path) -> None:
    catalog = load_catalog(output_root / "catalog")
    plugins_dir = output_root / "plugins"
    for target in TARGETS:
        target_dir = plugins_dir / target
        if target_dir.exists():
            shutil.rmtree(target_dir)
    for plugin in catalog.plugins.values():
        for target in TARGETS:
            plugin_out = plugins_dir / target / plugin.name
            (plugin_out / "skills").mkdir(parents=True, exist_ok=True)
            for skill_name in plugin.skills:
                write_skill(catalog.skills[skill_name], target, plugin_out / "skills" / skill_name)
        # hash after writing skills (manifests are written below with the new version)
        claude_dir = plugins_dir / "claude" / plugin.name
        new_hash = compute_plugin_hash(claude_dir)
        version = bump_version_if_changed(catalog.versions, plugin.name, new_hash)
        write_plugin_manifests(plugin, version, plugins_dir)
    (output_root / "catalog" / "plugin-versions.json").write_text(
        json.dumps(catalog.versions, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_marketplace_manifest(catalog, output_root)
```

Replace `main` body:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build shatterproof plugins.")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        build_all(args.output_root.resolve())
    except BuildError as e:
        print(f"build-plugins: {e}", file=sys.stderr)
        return 1
    print("build-plugins: ok", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Run tests, confirm PASS**

```bash
python -m pytest tests/test_build_plugins.py -v
```

Expected: 15 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build-plugins tests/test_build_plugins.py
git commit -m "build-plugins: marketplace manifest and end-to-end build_all"
```

---

### Task 7: `check-plugins-clean`

**Files:**
- Create: `scripts/check-plugins-clean` (executable bash)
- Create: `tests/test_check_plugins_clean.py`

- [ ] **Step 1: Write failing test for the clean check**

`tests/test_check_plugins_clean.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-plugins-clean"


def test_check_plugins_clean_exits_zero_when_in_sync():
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_plugins_clean_fails_when_drift_introduced(tmp_path):
    # Copy the working tree minimally — only catalog/, plugins/, scripts/, .claude-plugin/
    import shutil
    for top in ("catalog", "plugins", "scripts", ".claude-plugin"):
        src = REPO_ROOT / top
        if src.exists():
            shutil.copytree(src, tmp_path / top, symlinks=True)
    # Introduce drift: edit a generated file
    target = tmp_path / "plugins" / "claude" / "shatter" / "skills" / "install-shatter" / "SKILL.md"
    target.write_text("drift!\n", encoding="utf-8")
    result = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert result.returncode != 0
    assert "drift" in (result.stdout + result.stderr).lower() or "differ" in (result.stdout + result.stderr).lower()
```

(The second test depends on the full plan having been executed up through skill migration; it's listed here so the script's behavior is locked in, and it will start passing once those later tasks land.)

- [ ] **Step 2: Run the first test, confirm FAIL (script does not exist).**

- [ ] **Step 3: Write `scripts/check-plugins-clean`**

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$PWD}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Mirror catalog/ and the scripts into the work dir
mkdir -p "$work"
cp -a "$repo_root/catalog" "$work/catalog"
cp -a "$repo_root/scripts" "$work/scripts"

# Pre-populate plugin-versions.json from the repo so version bumps land identically
# (build-plugins will mutate this in $work, but never the real one).
python3 "$work/scripts/build-plugins" --output-root "$work" >/dev/null

fail=0
for top in plugins .claude-plugin; do
  if ! diff -r "$repo_root/$top" "$work/$top" > "$work/diff.$top.txt" 2>&1; then
    echo "drift detected in $top:" >&2
    cat "$work/diff.$top.txt" >&2
    fail=1
  fi
done

# Versions file must also match
if ! diff "$repo_root/catalog/plugin-versions.json" "$work/catalog/plugin-versions.json" > "$work/diff.versions.txt" 2>&1; then
  echo "drift detected in catalog/plugin-versions.json:" >&2
  cat "$work/diff.versions.txt" >&2
  fail=1
fi

exit $fail
```

Make executable:

```bash
chmod +x scripts/check-plugins-clean
```

- [ ] **Step 4: Run the first test, confirm PASS** (the in-sync test will need the rest of the plan to actually produce a clean tree, but after Task 19 it will pass; for now skip the in-sync test):

```bash
python -m pytest tests/test_check_plugins_clean.py::test_check_plugins_clean_fails_when_drift_introduced -v
```

Expected: PASS (assuming Task 19 has run; otherwise SKIP and re-run after Task 19).

- [ ] **Step 5: Commit**

```bash
git add scripts/check-plugins-clean tests/test_check_plugins_clean.py
git commit -m "check-plugins-clean script and drift test"
```

---

## Phase B — Migrate existing skills

### Task 8: Migrate `run-shatter` and fold in `review-shatter-output`

**Files:**
- Create: `catalog/skills/run-shatter/SKILL.md`
- Create: `catalog/skills/run-shatter/metadata.json`
- Create: `catalog/skills/run-shatter/scripts/run_targets.py` (moved from `scripts/run_targets.py`)
- Create: `catalog/skills/run-shatter/references/report-schema.md` (moved from `references/report-schema.md`)
- Modify: `tests/test_run_targets.py` (update `SCRIPT_PATH`)

- [ ] **Step 1: Move `scripts/run_targets.py` and `references/report-schema.md` into the new locations**

```bash
mkdir -p catalog/skills/run-shatter/scripts catalog/skills/run-shatter/references
git mv scripts/run_targets.py catalog/skills/run-shatter/scripts/run_targets.py
git mv references/report-schema.md catalog/skills/run-shatter/references/report-schema.md
```

- [ ] **Step 2: Update `tests/test_run_targets.py` to point at the new script path**

Change line 13 from:

```python
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_targets.py"
```

to:

```python
SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "catalog" / "skills" / "run-shatter" / "scripts" / "run_targets.py"
)
```

- [ ] **Step 3: Run the existing run-targets tests, confirm they still PASS**

```bash
python -m pytest tests/test_run_targets.py -v
```

Expected: 3 PASS (same as before the move).

- [ ] **Step 4: Write `catalog/skills/run-shatter/SKILL.md`** (combined run + review)

Write file content:

```markdown
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
```

- [ ] **Step 5: Write `catalog/skills/run-shatter/metadata.json`**

```json
{
  "recommended_model": "high",
  "audience": ["user"]
}
```

- [ ] **Step 6: Delete the old `skills/run-shatter/` and `skills/review-shatter-output/` directories**

```bash
git rm -r skills/run-shatter skills/review-shatter-output
```

- [ ] **Step 7: Run all tests so far, confirm PASS**

```bash
python -m pytest tests/test_build_plugins.py tests/test_run_targets.py -v
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add catalog/skills/run-shatter tests/test_run_targets.py
git rm -r skills/run-shatter skills/review-shatter-output 2>/dev/null || true
git commit -m "migrate run-shatter and fold in review-shatter-output"
```

---

### Task 9: Migrate `report-shatter-issues`

**Files:**
- Create: `catalog/skills/report-shatter-issues/SKILL.md`
- Create: `catalog/skills/report-shatter-issues/metadata.json`
- Create: `catalog/skills/report-shatter-issues/scripts/collect-context.sh` (moved)

- [ ] **Step 1: Move the helper script into the new location**

```bash
mkdir -p catalog/skills/report-shatter-issues/scripts
git mv scripts/collect-context.sh catalog/skills/report-shatter-issues/scripts/collect-context.sh
chmod +x catalog/skills/report-shatter-issues/scripts/collect-context.sh
```

- [ ] **Step 2: Write `catalog/skills/report-shatter-issues/SKILL.md`**

```markdown
---
name: report-shatter-issues
description: Write a markdown file that enumerates issues found during a Shatter review and includes relevant system and project context. Use when a downstream user wants a durable issue report instead of tracker-specific automation.
---

## Model Guidance

Recommended model: mid. Structured output assembly with light judgment on
which observations rise to the level of an issue.

## Purpose

Create a markdown report file, not a tracker ticket.

The report should be durable, portable, and detailed enough that a user
can keep it locally or paste it into GitHub later.

## Required inputs

- the review output from `run-shatter`
- the run directory and saved artifacts
- the relevant targets or files that were explored

Before writing the report, collect environment and project context with:

```bash
scripts/collect-context.sh --run-dir <run-dir> --target <path> --artifact <path> ...
```

Save that output alongside the report and include it in the final markdown
file.

## Report requirements

The report must be a markdown file with:

1. `Run summary`
2. `Environment and project context`
3. `Enumerated issues`
4. `Evidence and artifact references`

For the exact issue schema, read
`../../run-shatter/references/report-schema.md`.

## Issue selection

Include only actual issues or clearly labeled uncertainties. Do not
restate every observed behavior.

Good issue categories:

- probable Shatter bug
- report quality or usability problem
- incomplete exploration that blocks trust
- ambiguous result that needs confirmation

If the review found no issues, still write the markdown file and state
that no actionable issues were found.

## Per-issue content

For each issue, include:

- title
- severity
- category
- human description
- why it matters
- repro command
- expected versus actual behavior
- precise evidence
- related targets and artifact paths

Prefer one numbered issue section per finding.

## Required companion

- `scripts/collect-context.sh` (bundled with this skill)
```

- [ ] **Step 3: Write `catalog/skills/report-shatter-issues/metadata.json`**

```json
{
  "recommended_model": "mid",
  "audience": ["user"]
}
```

- [ ] **Step 4: Delete the old skill directory and now-empty `skills/` / `references/` parents**

```bash
git rm -r skills/report-shatter-issues
rmdir skills references 2>/dev/null || true
```

- [ ] **Step 5: Commit**

```bash
git add catalog/skills/report-shatter-issues
git commit -m "migrate report-shatter-issues into catalog/"
```

---

## Phase C — New skills

### Task 10: `update_usage_stanza.py` shared helper

This script ships in both `install-shatter` and `install-refute` (byte-identical copies). Tests reference the install-refute copy; a separate parity test asserts the two copies match.

**Files:**
- Create: `catalog/skills/install-refute/scripts/update_usage_stanza.py`
- Create: `catalog/skills/install-shatter/scripts/update_usage_stanza.py` (byte-identical copy)
- Create: `tests/test_update_usage_stanza.py`

- [ ] **Step 1: Failing tests for the helper**

`tests/test_update_usage_stanza.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HELPER = (
    Path(__file__).resolve().parents[1]
    / "catalog" / "skills" / "install-refute" / "scripts" / "update_usage_stanza.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("update_usage_stanza", HELPER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pick_target_prefers_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    m = _load()
    target, is_new = m.pick_target(tmp_path, "refute")
    assert target == tmp_path / "AGENTS.md"
    assert is_new is False


def test_pick_target_falls_back_to_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    m = _load()
    target, is_new = m.pick_target(tmp_path, "refute")
    assert target == tmp_path / "CLAUDE.md"
    assert is_new is False


def test_pick_target_creates_docs_when_neither_exists(tmp_path):
    m = _load()
    target, is_new = m.pick_target(tmp_path, "refute")
    assert target == tmp_path / "docs" / "refute-usage.md"
    assert is_new is True


def test_upsert_stanza_appends_when_missing():
    m = _load()
    out = m.upsert_stanza("# Existing\n", "refute", "## Refute\nbody\n")
    assert "<!-- refute:usage -->" in out
    assert "## Refute" in out


def test_upsert_stanza_replaces_in_place_idempotently():
    m = _load()
    text = (
        "# Existing\n\n"
        "<!-- refute:usage -->\n"
        "old stanza\n"
        "<!-- /refute:usage -->\n"
        "\n# After\n"
    )
    out1 = m.upsert_stanza(text, "refute", "## New\nbody\n")
    out2 = m.upsert_stanza(out1, "refute", "## New\nbody\n")
    assert out1 == out2
    assert "old stanza" not in out1
    assert "## New" in out1
    assert "# After" in out1


def test_two_copies_are_byte_identical():
    other = (
        Path(__file__).resolve().parents[1]
        / "catalog" / "skills" / "install-shatter" / "scripts" / "update_usage_stanza.py"
    )
    assert HELPER.read_bytes() == other.read_bytes()
```

- [ ] **Step 2: Run tests, confirm FAIL.**

- [ ] **Step 3: Write `catalog/skills/install-refute/scripts/update_usage_stanza.py`**

```python
#!/usr/bin/env python3
"""Insert or replace a tool's usage stanza in a project's primary agent doc."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def pick_target(project_root: Path, tool: str) -> tuple[Path, bool]:
    for candidate in ("AGENTS.md", "CLAUDE.md"):
        p = project_root / candidate
        if p.is_file():
            return p, False
    return project_root / "docs" / f"{tool}-usage.md", True


def build_stanza(tool: str, version: str | None, backends: list[str], skills: list[str]) -> str:
    label = tool.capitalize()
    lines = [f"## {label} Usage", ""]
    if version:
        lines.append(f"- Installed version: `{version}`")
    if backends:
        lines.append(f"- Backends installed: {', '.join(f'`{b}`' for b in backends)}")
    if skills:
        lines.append(f"- Suggested skills: {', '.join(f'`{s}`' for s in skills)}")
    lines.append("")
    lines.append(f"See upstream documentation for command reference.")
    return "\n".join(lines) + "\n"


def upsert_stanza(text: str, tool: str, stanza_body: str) -> str:
    open_marker = f"<!-- {tool}:usage -->"
    close_marker = f"<!-- /{tool}:usage -->"
    block = f"{open_marker}\n{stanza_body.rstrip()}\n{close_marker}"
    pattern = re.compile(
        rf"{re.escape(open_marker)}.*?{re.escape(close_marker)}",
        flags=re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(block, text)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "\n" + block + "\n"


def ensure_readme_pointer(project_root: Path, doc_path: Path, tool: str) -> None:
    readme = project_root / "README.md"
    rel = doc_path.relative_to(project_root).as_posix()
    open_marker = f"<!-- {tool}:pointer -->"
    close_marker = f"<!-- /{tool}:pointer -->"
    block = (
        f"{open_marker}\n"
        f"See [{tool} usage](./{rel}) for setup notes.\n"
        f"{close_marker}\n"
    )
    if readme.exists():
        existing = readme.read_text(encoding="utf-8")
        pattern = re.compile(
            rf"{re.escape(open_marker)}.*?{re.escape(close_marker)}\n?",
            flags=re.DOTALL,
        )
        if pattern.search(existing):
            new = pattern.sub(block, existing)
        else:
            if existing and not existing.endswith("\n"):
                existing += "\n"
            new = existing + "\n" + block
        readme.write_text(new, encoding="utf-8")
    else:
        readme.write_text(f"# Project\n\n{block}", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True, choices=["shatter", "refute"])
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--version", default=None)
    parser.add_argument("--backend", action="append", default=[])
    parser.add_argument("--skill", action="append", default=[])
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    target, is_new = pick_target(root, args.tool)
    stanza = build_stanza(args.tool, args.version, args.backend, args.skill)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        target.read_text(encoding="utf-8")
        if target.exists()
        else f"# {args.tool.capitalize()} Usage\n\n"
    )
    target.write_text(upsert_stanza(existing, args.tool, stanza), encoding="utf-8")
    if is_new:
        ensure_readme_pointer(root, target, args.tool)
    print(f"Updated {target.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make executable:

```bash
chmod +x catalog/skills/install-refute/scripts/update_usage_stanza.py
```

- [ ] **Step 4: Copy the helper byte-for-byte into install-shatter**

```bash
mkdir -p catalog/skills/install-shatter/scripts
cp catalog/skills/install-refute/scripts/update_usage_stanza.py \
   catalog/skills/install-shatter/scripts/update_usage_stanza.py
chmod +x catalog/skills/install-shatter/scripts/update_usage_stanza.py
```

- [ ] **Step 5: Run tests, confirm PASS**

```bash
python -m pytest tests/test_update_usage_stanza.py -v
```

Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add catalog/skills/install-refute/scripts catalog/skills/install-shatter/scripts tests/test_update_usage_stanza.py
git commit -m "add update_usage_stanza helper shared by both install skills"
```

---

### Task 11: `install-shatter` skill

**Files:**
- Create: `catalog/skills/install-shatter/SKILL.md`
- Create: `catalog/skills/install-shatter/metadata.json`
- (helper script already created in Task 10)

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: install-shatter
description: Install the `shatter` binary, run `shatter init` in the current project, and write a guarded usage stanza into the project's primary agent doc so future agents know how to use Shatter here.
---

## Model Guidance

Recommended model: low. Narrow install workflow with explicit commands and
a fixed end-state.

## Purpose

Set up Shatter for use in a downstream project. Install the CLI, initialize
the project, and leave a durable note in the project's agent doc.

## Behavior

### 1. Install the `shatter` binary

Pick the install path based on the user's intent:

- **Continuous build (default)**: run
  ```bash
  curl -sSL https://raw.githubusercontent.com/shatterproof-ai/shatter/main/install.sh | bash
  ```
  Default install location is `~/.local/bin`. Set `INSTALL_DIR=...` for a
  different destination.
- **Pinned build for CI or reproducibility**: instead of the above, pin a
  specific tag:
  ```bash
  curl -sSL https://raw.githubusercontent.com/shatterproof-ai/shatter/main/install.sh \
    | BUILD=continuous-YYYYMMDD-HHMM-<sha> bash
  ```
- **Build from source (contributors only)**: clone the repo, install Rust
  toolchain + Node.js 22+ + Go 1.24+ + `libclang`, then run
  `cargo build --release`. Use this only when the user requests it.

Verify with:

```bash
shatter --help
```

If the binary is not on `PATH`, point the user at the install-location
hint (`~/.local/bin` by default) and stop.

### 2. Initialize the project

From the project root, run:

```bash
shatter init
```

This creates `.shatter/config.yaml` if missing. Confirm to the user that
the file now exists.

### 3. Update the project's agent doc

Run the bundled helper:

```bash
python3 scripts/update_usage_stanza.py \
  --tool shatter \
  --project-root . \
  --version "$(shatter --version 2>/dev/null | head -1)" \
  --skill run-shatter \
  --skill report-shatter-issues
```

The helper picks the destination by this order:

1. `AGENTS.md` if it exists.
2. Else `CLAUDE.md` if it exists.
3. Else create `docs/shatter-usage.md` and add a one-liner in `README.md`
   pointing at it.

The stanza is bracketed by `<!-- shatter:usage -->` and
`<!-- /shatter:usage -->`. Re-running this skill replaces the stanza in
place.

### 4. Hand off

Suggest `run-shatter` for the user's first end-to-end run; the run skill
will discover and run any integrated targets the project has.

## Out of scope

- Adding `shatter` wrappers to `package.json` / `Taskfile.yml` /
  `Makefile` (covered by `add-shatter-target`, deferred).
- CI wiring (covered by `wire-shatter-ci`, deferred).
- Diagnosing existing Shatter installs (covered by `shatter-doctor`,
  deferred).

## Required companion

- `scripts/update_usage_stanza.py` (bundled with this skill, byte-identical
  to the copy in `install-refute`)
```

- [ ] **Step 2: Write metadata.json**

```json
{
  "recommended_model": "low",
  "audience": ["user"]
}
```

- [ ] **Step 3: Commit**

```bash
git add catalog/skills/install-shatter/SKILL.md catalog/skills/install-shatter/metadata.json
git commit -m "add install-shatter skill"
```

---

### Task 12: `install-refute` skill

**Files:**
- Create: `catalog/skills/install-refute/SKILL.md`
- Create: `catalog/skills/install-refute/metadata.json`
- (helper script already created in Task 10)

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: install-refute
description: Install the `refute` binary and the LSP backends for the languages used in the current project, verify the install, and write a guarded usage stanza into the project's primary agent doc.
---

## Model Guidance

Recommended model: low. Narrow install workflow with explicit commands and
a fixed end-state.

## Purpose

Set up Refute for use in a downstream project. Detect the languages
present in the project, install the correct LSP backends for those
languages, and leave a durable note in the project's agent doc.

## Behavior

### 1. Detect target languages

Inspect the project root for these markers and record the languages
present:

- `go.mod` → Go
- `Cargo.toml` → Rust
- `package.json` → TypeScript / JavaScript

If none are present, ask the user which language to target; do not guess.

### 2. Install `refute`

Pick the install path based on the project:

- **Go project, Go 1.24+ (preferred)**: run
  ```bash
  go get -tool github.com/shatterproof-ai/refute/cmd/refute@latest
  ```
  Verify with `go tool refute version`. Pinning a concrete release tag is
  handled by the separate `pin-refute` skill once it ships.
- **Personal shell use (non-Go project, user wants a global binary)**:
  ```bash
  go install github.com/shatterproof-ai/refute/cmd/refute@latest
  ```
  Verify with `refute version`.
- **Build from source (rare; user requested)**: clone the repo and
  `go build ./cmd/refute`.

Refuse to install if Go is not on `PATH`; point the user at the official
Go install docs and stop.

### 3. Install backends for the project's languages

For each detected language, install the matching backend if missing:

- Go (always for a Go project):
  ```bash
  go install golang.org/x/tools/gopls@latest
  ```
- Rust:
  ```bash
  rustup component add rust-analyzer
  ```
- TypeScript:
  ```bash
  npm install -g typescript-language-server typescript
  ```

Skip backends for languages the project does not use.

### 4. Verify

Run `refute version` (or `go tool refute version`) and confirm the output.

### 5. Update the project's agent doc

Run the bundled helper:

```bash
python3 scripts/update_usage_stanza.py \
  --tool refute \
  --project-root . \
  --version "$(refute version 2>/dev/null | head -1 || go tool refute version 2>/dev/null | head -1)" \
  --backend gopls \
  --backend rust-analyzer \
  --backend typescript-language-server \
  --skill refute-doctor
```

Pass only the `--backend` flags for backends that were actually installed.

The helper picks the destination by this order:

1. `AGENTS.md` if it exists.
2. Else `CLAUDE.md` if it exists.
3. Else create `docs/refute-usage.md` and add a one-liner in `README.md`
   pointing at it.

The stanza is bracketed by `<!-- refute:usage -->` and
`<!-- /refute:usage -->`. Re-running this skill replaces the stanza in
place.

### 6. Hand off to `refute-doctor`

Tell the user to run `refute-doctor` next to verify the install is fully
working for the project's languages.

## Out of scope

- Pinning to a specific release (covered by `pin-refute`, deferred).
- Performing any refactoring (covered by `refute-rename`, deferred).
- Installing language toolchains that the project already requires (Go
  itself, Node.js, rustup) — assumed present.

## Required companion

- `scripts/update_usage_stanza.py` (bundled with this skill, byte-identical
  to the copy in `install-shatter`)
```

- [ ] **Step 2: Write metadata.json**

```json
{
  "recommended_model": "low",
  "audience": ["user"]
}
```

- [ ] **Step 3: Commit**

```bash
git add catalog/skills/install-refute/SKILL.md catalog/skills/install-refute/metadata.json
git commit -m "add install-refute skill"
```

---

### Task 13: `refute-doctor` skill

**Files:**
- Create: `catalog/skills/refute-doctor/SKILL.md`
- Create: `catalog/skills/refute-doctor/metadata.json`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: refute-doctor
description: Run `refute doctor` for a project, parse the support matrix, report the status of each language's backend and the available refactoring operations, and recommend the exact remediation command for each problem.
---

## Model Guidance

Recommended model: mid. Procedural diagnostic with light judgment on
which language entries actually matter for this project.

## Purpose

Tell the user whether Refute is healthy for the languages this project
actually uses, and exactly what to fix when it is not.

## Required inputs

- The path to the project root (defaults to the current working
  directory).

## Behavior

### 1. Run the doctor

From the project root:

```bash
refute doctor
```

If the project uses Refute as a Go-tool dependency rather than a global
binary, run instead:

```bash
go tool refute doctor
```

Capture the output. If the command is missing, point the user at
`install-refute` and stop.

### 2. Detect relevant languages

Inspect the project root for these markers:

- `go.mod` → Go
- `Cargo.toml` → Rust
- `package.json` → TypeScript / JavaScript

Restrict the report to the languages present in the project. Mention but
do not block on languages the doctor reports for which the project does
not use.

### 3. Report

For each language present in the project, report:

- backend status (ready / missing / out of date / extension missing)
- which refactoring operations are currently usable
- the exact remediation command, taken from the doctor output, when the
  backend is not ready

Use this shape:

```
## Refute Health

- Go (gopls): READY at v0.x.y — rename, reference search usable
- Rust (rust-analyzer): MISSING
  Fix: rustup component add rust-analyzer
- TypeScript: BACKEND OUT OF DATE
  Fix: npm install -g typescript-language-server@latest
```

### 4. Summary

Close with a one-line summary: "Refute is ready for the languages this
project uses" or "Refute is blocked on N backends — see above".

## Out of scope

- Installing backends (covered by `install-refute`).
- Performing refactorings (covered by `refute-rename`, deferred).
- Pinning versions (covered by `pin-refute`, deferred).
```

- [ ] **Step 2: Write metadata.json**

```json
{
  "recommended_model": "mid",
  "audience": ["user"]
}
```

- [ ] **Step 3: Commit**

```bash
git add catalog/skills/refute-doctor/SKILL.md catalog/skills/refute-doctor/metadata.json
git commit -m "add refute-doctor skill"
```

---

## Phase D — Suite-level tests

### Task 14: `test_skills_load.py`

**Files:**
- Create: `tests/test_skills_load.py`

- [ ] **Step 1: Write the test**

```python
from __future__ import annotations

import json
import re
import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "catalog" / "skills"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _all_skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_skill_has_valid_frontmatter(skill_dir: Path):
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file(), f"{skill_md} missing"
    m = FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    assert m, f"{skill_md} missing frontmatter"
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    assert fm["name"] == skill_dir.name
    assert "description" in fm and fm["description"]
    assert set(fm) == {"name", "description"}, f"extra keys: {set(fm) - {'name','description'}}"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_skill_metadata_parses(skill_dir: Path):
    metadata = skill_dir / "metadata.json"
    assert metadata.is_file(), f"{metadata} missing"
    data = json.loads(metadata.read_text(encoding="utf-8"))
    assert data.get("recommended_model") in {"low", "mid", "high"}, f"bad recommended_model in {metadata}"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_skill_companion_scripts_are_executable(skill_dir: Path):
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return
    for script in scripts_dir.iterdir():
        if script.is_file():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script} is not executable"
```

- [ ] **Step 2: Run tests, confirm PASS**

```bash
python -m pytest tests/test_skills_load.py -v
```

Expected: 15 PASS (5 skills × 3 parametrized tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_skills_load.py
git commit -m "add suite-level skill load tests"
```

---

### Task 15: `test_overlay_composition.py`

**Files:**
- Create: `tests/test_overlay_composition.py`

(None of the v1 skills ship overlays; this test guards the contract so the
first skill that adds one cannot break it.)

- [ ] **Step 1: Write the test**

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build-plugins"


def _load_build():
    spec = importlib.util.spec_from_file_location("build_plugins", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_skill_with_overlay(tmp_path: Path, body: str, overlay_name: str, overlay_text: str) -> Path:
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\n\n" + body + "\n", encoding="utf-8"
    )
    (skill / "metadata.json").write_text("{}\n", encoding="utf-8")
    (skill / overlay_name).write_text(overlay_text, encoding="utf-8")
    return skill


def test_overlay_with_frontmatter_is_rejected(tmp_path):
    build = _load_build()
    _write_skill_with_overlay(tmp_path, "body", "CLAUDE.md", "---\nx: y\n---\n## hi\n")
    with pytest.raises(build.BuildError, match="must not contain frontmatter"):
        build.load_skill(tmp_path / "skills" / "demo")


def test_overlay_must_start_with_h2(tmp_path):
    build = _load_build()
    _write_skill_with_overlay(tmp_path, "body", "CLAUDE.md", "no heading here\n")
    with pytest.raises(build.BuildError, match="level-2 heading"):
        build.load_skill(tmp_path / "skills" / "demo")


def test_composed_skill_has_base_then_overlay(tmp_path):
    build = _load_build()
    _write_skill_with_overlay(tmp_path, "base body", "CLAUDE.md", "## Claude only\nextra\n")
    skill = build.load_skill(tmp_path / "skills" / "demo")
    composed = build.compose_skill(skill, "claude")
    assert composed.index("base body") < composed.index("## Claude only")
    plain = build.compose_skill(skill, "codex")
    assert "## Claude only" not in plain
```

- [ ] **Step 2: Run tests, confirm PASS**

```bash
python -m pytest tests/test_overlay_composition.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_overlay_composition.py
git commit -m "add overlay composition contract tests"
```

---

### Task 16: `test_marketplace_manifest.py`

**Files:**
- Create: `tests/test_marketplace_manifest.py`

- [ ] **Step 1: Write the test**

```python
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_lists_exactly_catalog_plugins():
    plugins = json.loads((REPO_ROOT / "catalog" / "plugins.json").read_text())["plugins"]
    mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    listed = [p["name"] for p in mp["plugins"]]
    assert sorted(listed) == sorted(plugins.keys())


def test_marketplace_sources_resolve_to_existing_dirs():
    mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in mp["plugins"]:
        src = REPO_ROOT / entry["source"].lstrip("./")
        assert src.is_dir(), f"{src} missing for {entry['name']}"
        assert (src / ".claude-plugin" / "plugin.json").is_file()


def test_marketplace_versions_match_plugin_manifests():
    mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in mp["plugins"]:
        manifest = json.loads(
            (REPO_ROOT / entry["source"].lstrip("./") / ".claude-plugin" / "plugin.json").read_text()
        )
        assert manifest["version"] == entry["version"]
```

- [ ] **Step 2: Run tests** — will FAIL until Task 19 runs the builder for the first time. That's expected; the test is locked-in early so Task 19's success criterion is checkable.

- [ ] **Step 3: Commit**

```bash
git add tests/test_marketplace_manifest.py
git commit -m "add marketplace manifest contract tests"
```

---

### Task 17: `test_build_idempotent.py`

**Files:**
- Create: `tests/test_build_idempotent.py`

- [ ] **Step 1: Write the test**

```python
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD = REPO_ROOT / "scripts" / "build-plugins"


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(f.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def test_double_build_produces_zero_diff(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    for top in ("catalog", "scripts"):
        shutil.copytree(REPO_ROOT / top, work / top, symlinks=True)
    subprocess.run([str(BUILD), "--output-root", str(work)], check=True)
    h1 = _hash_tree(work / "plugins")
    v1 = (work / "catalog" / "plugin-versions.json").read_text(encoding="utf-8")
    subprocess.run([str(BUILD), "--output-root", str(work)], check=True)
    h2 = _hash_tree(work / "plugins")
    v2 = (work / "catalog" / "plugin-versions.json").read_text(encoding="utf-8")
    assert h1 == h2
    assert v1 == v2
```

- [ ] **Step 2: Run tests, confirm PASS** (assumes Phase B and C catalog content is in place):

```bash
python -m pytest tests/test_build_idempotent.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_build_idempotent.py
git commit -m "add build idempotency test"
```

---

### Task 18: `test_install_skills_update_docs.py`

End-to-end tests for the helper invoked by both install skills.

**Files:**
- Create: `tests/test_install_skills_update_docs.py`

- [ ] **Step 1: Write the test**

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HELPER = (
    Path(__file__).resolve().parents[1]
    / "catalog" / "skills" / "install-refute" / "scripts" / "update_usage_stanza.py"
)


def _run_helper(project_root: Path, tool: str, *extra: str) -> None:
    subprocess.run(
        [sys.executable, str(HELPER), "--tool", tool, "--project-root", str(project_root), *extra],
        check=True,
    )


def test_stanza_lands_in_agents_md_when_present(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n\nExisting.\n", encoding="utf-8")
    _run_helper(tmp_path, "refute", "--version", "0.1.0", "--backend", "gopls")
    contents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- refute:usage -->" in contents
    assert "Existing." in contents
    assert "`gopls`" in contents


def test_stanza_lands_in_claude_md_when_only_claude_present(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    _run_helper(tmp_path, "refute")
    assert (tmp_path / "CLAUDE.md").read_text().count("<!-- refute:usage -->") == 1
    assert not (tmp_path / "AGENTS.md").exists()


def test_stanza_creates_docs_and_readme_when_neither_exists(tmp_path):
    _run_helper(tmp_path, "refute", "--version", "0.1.0")
    assert (tmp_path / "docs" / "refute-usage.md").is_file()
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "<!-- refute:pointer -->" in readme
    assert "docs/refute-usage.md" in readme


def test_rerun_is_idempotent(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    _run_helper(tmp_path, "refute", "--version", "0.1.0")
    first = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    _run_helper(tmp_path, "refute", "--version", "0.1.0")
    second = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
```

- [ ] **Step 2: Run tests, confirm PASS**

```bash
python -m pytest tests/test_install_skills_update_docs.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_install_skills_update_docs.py
git commit -m "add install-skill doc-update integration tests"
```

---

## Phase E — Build, CI, docs, final cleanup

### Task 19: Run `build-plugins` for the first time and commit generated output

**Files:**
- Create (generated): `plugins/claude/shatter/...`, `plugins/codex/shatter/...`, `plugins/claude/refute/...`, `plugins/codex/refute/...`
- Create (generated): `.claude-plugin/marketplace.json`
- Modify (generated): `catalog/plugin-versions.json`

- [ ] **Step 1: Run the builder**

```bash
python3 scripts/build-plugins
```

Expected stderr: `build-plugins: ok`.

- [ ] **Step 2: Inspect the generated tree**

```bash
ls plugins/claude/shatter plugins/codex/shatter plugins/claude/refute plugins/codex/refute
cat .claude-plugin/marketplace.json
cat catalog/plugin-versions.json
```

Confirm:
- both plugins exist in both target trees
- `marketplace.json` lists both plugins
- both plugins now have non-empty `content_hash` in plugin-versions.json
- versions stay at `0.1.0` (initial; patch=0 is the manual-bump anchor, so the first build only records the hash — see `docs/conventions/versioning.md`)

- [ ] **Step 3: Run the marketplace and idempotency tests, confirm PASS**

```bash
python -m pytest tests/test_marketplace_manifest.py tests/test_build_idempotent.py -v
```

Expected: green.

- [ ] **Step 4: Run `check-plugins-clean` and confirm exit 0**

```bash
scripts/check-plugins-clean
echo $?
```

Expected: `0`.

- [ ] **Step 5: Commit generated output**

```bash
git add plugins/ .claude-plugin/marketplace.json catalog/plugin-versions.json
git commit -m "build: first generated plugin tree and marketplace.json"
```

---

### Task 20: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  workflow_dispatch: {}

jobs:
  build-clean:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Check generated plugins are in sync with catalog
        run: scripts/check-plugins-clean

  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install pytest
        run: pip install pytest
      - name: Run tests
        run: python -m pytest tests/ -v
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: build-clean gate and pytest workflow"
```

---

### Task 21: Top-level docs (README, DESIGN, AGENTS, CLAUDE)

**Files:**
- Create: `README.md`
- Create: `DESIGN.md`
- Create: `AGENTS.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# shatter-agents — Shatterproof Marketplace

A plugin marketplace for [Shatter](https://github.com/shatterproof-ai/shatter)
and [Refute](https://github.com/shatterproof-ai/refute), targeting Claude
Code and OpenAI Codex.

## Plugins

| Plugin | Description |
|---|---|
| `shatter` | Install, run, and review Shatter; draft markdown issue reports. |
| `refute`  | Install Refute and diagnose its setup for symbol-aware refactoring. |

## Install (Claude Code)

Add the marketplace to your settings:

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": {
      "source": { "source": "github", "repo": "shatterproof-ai/shatter-agents" }
    }
  }
}
```

Then install either or both plugins from the Claude Code plugin chooser.

See [`docs/installing-plugins.md`](docs/installing-plugins.md) for Codex
install instructions and offline notes.

## Repository structure

- `catalog/` — canonical sources for skills and plugin metadata.
- `plugins/` — generated, committed plugin trees consumed by Claude Code
  and Codex. Do not edit by hand; edit `catalog/` and rebuild.
- `scripts/build-plugins` — regenerates `plugins/` and
  `.claude-plugin/marketplace.json`. Patch versions auto-bump on content
  change.
- `scripts/check-plugins-clean` — CI gate that fails if generated output
  has drifted from the canonical sources.

See [`DESIGN.md`](DESIGN.md) and
[`docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md`](docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md)
for the full design.

## Tracker

Issues live in the in-repo Beads tracker (`.beads/`). Run `bd list` to
see what is open.
```

- [ ] **Step 2: Write `DESIGN.md`** (short pointer)

```markdown
# Shatterproof Marketplace — Design

This is a short pointer file. The canonical design document is at
[`docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md`](docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md).

Conventions split out into their own documents:

- [`docs/conventions/overlays.md`](docs/conventions/overlays.md) — how
  `CLAUDE.md` and `CODEX.md` overlays compose with shared `SKILL.md`.
- [`docs/conventions/companion-files.md`](docs/conventions/companion-files.md)
  — semantics of `references/` and `scripts/` under each skill.
- [`docs/conventions/versioning.md`](docs/conventions/versioning.md) —
  auto-versioning, content-hash inputs, and how to do a manual major/minor
  bump.
```

- [ ] **Step 3: Write `AGENTS.md`**

```markdown
# Agent Instructions

## What this repo is

`shatter-agents` is the **shatterproof marketplace**: a plugin marketplace
for Claude Code and Codex that ships two plugins (`shatter`, `refute`)
built from canonical sources under `catalog/`.

## Rules for changes

1. **Never edit `plugins/` by hand.** That tree is generated by
   `scripts/build-plugins` from `catalog/`. Edit the canonical sources and
   rebuild.
2. **Always run `scripts/build-plugins` before committing** a change to
   `catalog/`. CI runs `scripts/check-plugins-clean` and will fail if
   `plugins/` or `.claude-plugin/marketplace.json` is out of sync.
3. **Patch versions auto-bump.** A content change in `catalog/` will cause
   `scripts/build-plugins` to bump the affected plugin's patch version
   automatically. For major or minor bumps, edit
   `catalog/plugin-versions.json` directly; the builder accepts any
   version greater than or equal to its auto-bump target.
4. **SKILL.md frontmatter is `name` and `description` only.** Other
   per-skill metadata goes in `metadata.json` next to the SKILL.md.
5. **Overlays append.** `CLAUDE.md` and `CODEX.md` inside a skill
   directory must start with a level-2 heading and contain no frontmatter.

## Issue tracker

Beads (`bd`) is the tracker for this repo. Common commands:

```bash
bd ready                    # show issues ready to start
bd show <id>                # full issue
bd update <id> --status in_progress
bd close <id> --reason "<merge-sha> landed on main"
```

Closure requires the merge SHA to be reachable from `main`. Closing
prematurely will be caught and reverted.

## Landing changes

Merge feature branches into `main` with `git merge --no-ff` and push to
`origin main`. Never open pull requests against this repo.
```

- [ ] **Step 4: Write `CLAUDE.md`**

```markdown
# Claude-specific instructions

See [`AGENTS.md`](AGENTS.md) for the canonical agent guide. This file
exists so Claude Code's automatic agent-doc discovery finds something
here; the content of interest is in AGENTS.md.
```

- [ ] **Step 5: Commit**

```bash
git add README.md DESIGN.md AGENTS.md CLAUDE.md
git commit -m "docs: top-level repo guides"
```

---

### Task 22: Conventions docs and install guide

**Files:**
- Create: `docs/installing-plugins.md`
- Create: `docs/conventions/overlays.md`
- Create: `docs/conventions/companion-files.md`
- Create: `docs/conventions/versioning.md`

- [ ] **Step 1: Write `docs/installing-plugins.md`**

```markdown
# Installing Shatterproof Plugins

## Claude Code

Add the marketplace to your settings (`~/.claude/settings.json` for
home-scope, or `.claude/settings.local.json` for project-scope):

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": {
      "source": { "source": "github", "repo": "shatterproof-ai/shatter-agents" }
    }
  }
}
```

Then `/plugins install shatterproof:shatter` or
`/plugins install shatterproof:refute`.

## OpenAI Codex

Codex plugins from this marketplace can be installed from the generated
`plugins/codex/<name>/` directories. The Codex side of this marketplace
does not currently register custom slash commands; invoke skills by name
in your prompt instead, for example:

> Use the `install-shatter` skill to set up Shatter in this project.

## Offline install

Clone the repo and point your Claude Code config at the local path:

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": { "source": { "source": "path", "path": "/abs/path/to/shatter-agents" } }
  }
}
```
```

- [ ] **Step 2: Write `docs/conventions/overlays.md`**

```markdown
# Skill Overlays

A canonical skill lives under `catalog/skills/<name>/SKILL.md`. When the
behavior is identical across Claude Code and Codex, that file is the
entire skill.

When a skill needs target-specific text, add an overlay file in the same
directory:

- `CLAUDE.md` — appended to the composed Claude Code skill body
- `CODEX.md` — appended to the composed Codex skill body

Overlays must:

- Start with a level-2 heading (`## ...`).
- Contain no YAML frontmatter (only the canonical `SKILL.md` defines the
  frontmatter).

The builder appends each overlay verbatim after the canonical body,
separated by a horizontal rule.

## Why `metadata.json` instead of frontmatter keys

Per-skill metadata such as `recommended_model` lives in `metadata.json`
next to `SKILL.md`, not in the frontmatter. Reasons:

1. **Semantic non-portability.** The three-bucket `low|mid|high` mapping
   is Claude-shaped (Haiku / Sonnet / Opus). Codex, Gemini, and local
   model runtimes do not share a single three-tier hierarchy.
2. **Schema non-portability.** SKILL.md frontmatter is the typed contract
   the host runtime parses. Unknown keys happen to work today but are not
   part of any documented spec.
3. **Temporal non-portability.** Bucket labels have no version pin. The
   prose `## Model Guidance` section in the body ages better than the
   label.

`metadata.json` is plain JSON, copied verbatim into generated plugins.
Any future discovery tool can read it without touching the SKILL contract.
```

- [ ] **Step 3: Write `docs/conventions/companion-files.md`**

```markdown
# Skill Companion Files

A skill directory may include companion files alongside `SKILL.md` and
`metadata.json`:

```
catalog/skills/<name>/
├── SKILL.md
├── metadata.json
├── references/         # data the skill body cites
└── scripts/            # deterministic helpers the skill body invokes
```

## When to write a companion script vs prose

Push logic into a companion script when it is:

- repeatable and benefits from machine-checkable output (JSON)
- stateful or high-cost if misclassified
- dependent on repo facts, git state, or precise file parsing

Keep logic in `SKILL.md` prose when it is:

- qualitative or judgment-heavy
- dependent on user preferences or trade-offs
- policy, framing, or workflow guidance

## Layout in generated plugins

`references/` and `scripts/` are copied verbatim into
`plugins/<target>/<plugin>/skills/<skill>/`. Executable bits on scripts
are preserved.

## Cross-skill references

Two skills in the **same plugin** can reference each other's companion
files via relative paths. Example: `report-shatter-issues/SKILL.md`
references `../../run-shatter/references/report-schema.md` because both
skills ship in the `shatter` plugin.

Cross-plugin references are not supported. If two plugins genuinely need
the same helper, duplicate it (the v1 example is
`update_usage_stanza.py`, byte-identical in `install-shatter` and
`install-refute`).
```

- [ ] **Step 4: Write `docs/conventions/versioning.md`**

```markdown
# Plugin Versioning

Each plugin's current version is stored in
`catalog/plugin-versions.json`:

```json
{
  "shatter": { "version": "0.1.1", "content_hash": "sha256:..." },
  "refute":  { "version": "0.1.0", "content_hash": "sha256:..." }
}
```

## Auto-bumped patches

When `scripts/build-plugins` runs, it computes a content hash over each
plugin's freshly generated tree. The hash inputs:

- sorted file paths within `plugins/claude/<plugin>/`
- per-file SHA-256
- excludes the `version` field of the manifest itself (so a version bump
  alone does not feed back into the hash)

If the new hash differs from the recorded hash:

- If the recorded `version` has `patch > 0`, the builder bumps the patch by
  one and writes the new hash.
- If the recorded `version` has `patch == 0`, the builder leaves the
  version alone and only updates the hash. `patch == 0` is the
  **manual-bump anchor**: it indicates the version was just set by a
  human (initial `0.1.0`, or a manual bump to `1.0.0` / `2.3.0`), and the
  builder should not auto-bump it on the first content-change after.

If the hash matches, no-op.

## Manual major or minor bumps

Edit `catalog/plugin-versions.json` directly and set `version` to your
target — always with `patch = 0`. Example: bumping `1.2.7` to `2.0.0`.
The next build sees the patch=0 anchor and records the new hash without
auto-bumping; subsequent content changes resume the auto-bump at
`2.0.1`, `2.0.2`, and so on.

## Why this approach

- No separate bump script (bento's `bump-plugin-versions` is replaced by
  the builder).
- Idempotent: running the builder twice in a row never changes either
  the versions file or the generated tree.
- CI catches missed rebuilds via `scripts/check-plugins-clean`, which
  diffs the committed `plugins/` and versions file against a fresh build.
```

- [ ] **Step 5: Commit**

```bash
git add docs/installing-plugins.md docs/conventions/
git commit -m "docs: install guide and per-topic conventions"
```

---

### Task 23: Final cleanup — delete obsolete files

**Files:**
- Delete: `.codex-plugin/plugin.json`
- Delete: empty `.codex-plugin/`, `skills/`, `references/`, `scripts/run_targets.py` parent if empty (handled by earlier moves)

- [ ] **Step 1: Delete the root-level Codex plugin manifest** (superseded by `plugins/codex/{shatter,refute}/.codex-plugin/plugin.json`)

```bash
git rm .codex-plugin/plugin.json
rmdir .codex-plugin 2>/dev/null || true
```

- [ ] **Step 2: Confirm no orphan dirs remain**

```bash
ls skills references .codex-plugin 2>&1 || true
```

Expected: all "No such file or directory".

- [ ] **Step 3: Re-run the full test suite plus check-plugins-clean**

```bash
python -m pytest tests/ -v && scripts/check-plugins-clean
```

Expected: all green, exit 0.

- [ ] **Step 4: Commit cleanup**

```bash
git add -A
git commit -m "remove obsolete root-level .codex-plugin"
```

---

### Task 24: Land work and close `agents-gre`

**Files:**
- None (tracker-only mutation)

- [ ] **Step 1: Merge the feature branch into `main`** (assuming the implementer was on a branch; if direct on main, skip)

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff <implementation-branch>
git push origin main
```

- [ ] **Step 2: Capture the merge SHA**

```bash
MERGE_SHA=$(git rev-parse main)
echo "$MERGE_SHA"
```

- [ ] **Step 3: Verify the merge SHA is reachable from `main`**

```bash
git merge-base --is-ancestor "$MERGE_SHA" main && echo "ok"
```

Expected: `ok`.

- [ ] **Step 4: Close `agents-gre` with the merge evidence**

```bash
bd close agents-gre --reason "$MERGE_SHA landed on main"
```

- [ ] **Step 5: Confirm closure**

```bash
bd show agents-gre | head -20
```

Expected: status `closed` with the reason line including the merge SHA.

---

## Self-review checklist

After the implementer finishes, run through:

- [ ] All 24 tasks committed
- [ ] `python -m pytest tests/ -v` is green
- [ ] `scripts/check-plugins-clean` exits 0
- [ ] `bd list` shows `agents-gre` closed and the other deferred issues
      still open with their correct dependencies
- [ ] `cat .claude-plugin/marketplace.json` lists `shatter` and `refute`
- [ ] `ls catalog/skills/` shows the 5 v1 skills
- [ ] No `skills/`, `references/`, `.codex-plugin/` directories at repo
      root
- [ ] README, DESIGN.md, AGENTS.md, CLAUDE.md, the conventions docs, and
      the install guide all exist
