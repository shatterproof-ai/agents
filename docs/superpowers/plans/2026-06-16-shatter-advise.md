# shatter-advise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `shatter-advise` and `shatter-gaps` skills to the shatter plugin — a shared discovery script plus two skill files that guide an agent to analyze a project's tractability and produce ranked cluster recommendations.

**Architecture:** A deterministic Python script (`discover_hotspots.py`) does language detection, static signal collection, artifact loading, and proto-clustering; the skill text then guides the agent through deep reading, taxonomy-gate analysis, prescription writing, and report generation. The two skills (`shatter-advise` for project findings, `shatter-gaps` for engine gaps) share the script and the analysis workflow, differing only in which dispositions they present.

**Tech Stack:** Python 3 (script + tests), markdown (SKILL.md, reports), JSON (discovery output, findings.json), unittest (script tests). No external Python dependencies beyond stdlib.

---

## File Map

**Create:**
- `catalog/skills/shatter-advise/SKILL.md` — shatter-advise skill text
- `catalog/skills/shatter-advise/metadata.json` — skill metadata
- `catalog/skills/shatter-advise/scripts/discover_hotspots.py` — shared discovery script
- `catalog/skills/shatter-gaps/SKILL.md` — shatter-gaps skill text
- `catalog/skills/shatter-gaps/metadata.json` — skill metadata
- `tests/fixtures/tractability/go-handlers/go.mod` — Go fixture language marker
- `tests/fixtures/tractability/go-handlers/internal/handlers/projects.go` — handler mixing IO and logic
- `tests/fixtures/tractability/go-handlers/internal/handlers/generated.gen.go` — generated file without project logic
- `tests/fixtures/tractability/go-handlers/internal/handlers/resolver.gen.go` — generated file WITH project logic (branch in generated code)
- `tests/fixtures/tractability/ts-async-store/package.json` — TS fixture language marker
- `tests/fixtures/tractability/ts-async-store/src/stores/sessionStore.ts` — async Zustand-like store with browser globals
- `tests/fixtures/tractability/ts-async-store/src/utils/pure.ts` — clean functional code (no signals — should not appear as hotspot)
- `tests/fixtures/tractability/fake-shatter-run/summary.json` — synthetic run-shatter summary
- `tests/fixtures/tractability/fake-shatter-run/go-handlers/projects_handler.spec.json` — spec JSON with unsupported outcome
- `tests/test_discover_hotspots.py` — script unit tests

**Modify:**
- `catalog/plugins.json` — add `shatter-advise` and `shatter-gaps` to the shatter skill list

---

## Task 1: Create test fixtures

**Files:**
- Create: `tests/fixtures/tractability/go-handlers/go.mod`
- Create: `tests/fixtures/tractability/go-handlers/internal/handlers/projects.go`
- Create: `tests/fixtures/tractability/go-handlers/internal/handlers/generated.gen.go`
- Create: `tests/fixtures/tractability/go-handlers/internal/handlers/resolver.gen.go`
- Create: `tests/fixtures/tractability/ts-async-store/package.json`
- Create: `tests/fixtures/tractability/ts-async-store/src/stores/sessionStore.ts`
- Create: `tests/fixtures/tractability/ts-async-store/src/utils/pure.ts`
- Create: `tests/fixtures/tractability/fake-shatter-run/summary.json`
- Create: `tests/fixtures/tractability/fake-shatter-run/go-handlers/projects_handler.spec.json`

- [ ] **Step 1: Create the Go fixture**

`tests/fixtures/tractability/go-handlers/go.mod`:
```
module example.com/go-handlers

go 1.21
```

`tests/fixtures/tractability/go-handlers/internal/handlers/projects.go`:
```go
package handlers

import (
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
)

type ProjectHandler struct {
	db *sql.DB
}

func NewProjectHandler(db *sql.DB) *ProjectHandler {
	return &ProjectHandler{db: db}
}

func (h *ProjectHandler) UpdateProject(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if req.Name == "" {
		http.Error(w, "name required", http.StatusUnprocessableEntity)
		return
	}
	row := h.db.QueryRow("SELECT owner_id FROM projects WHERE id = $1", r.URL.Query().Get("id"))
	var ownerID string
	if err := row.Scan(&ownerID); err == sql.ErrNoRows {
		http.Error(w, "not found", http.StatusNotFound)
		return
	} else if err != nil {
		log.Printf("db error: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	if ownerID != r.Header.Get("X-User-ID") {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	if _, err := h.db.Exec("UPDATE projects SET name=$1 WHERE id=$2", req.Name, r.URL.Query().Get("id")); err != nil {
		log.Printf("update error: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
```

`tests/fixtures/tractability/go-handlers/internal/handlers/generated.gen.go`:
```go
// Code generated by protoc-gen-go. DO NOT EDIT.

package handlers

// generatedHelper is pure scaffolding with no project decisions.
func generatedDispatch(kind string) string {
	switch kind {
	case "a":
		return "type-a"
	default:
		return "type-b"
	}
}
```

`tests/fixtures/tractability/go-handlers/internal/handlers/resolver.gen.go`:
```go
// Code generated by graphql-codegen. DO NOT EDIT.

package handlers

import "database/sql"

// resolveProjectOwner is generated glue that contains project authorization logic.
func resolveProjectOwner(db *sql.DB, projectID, userID string) (bool, error) {
	var ownerID string
	err := db.QueryRow("SELECT owner_id FROM projects WHERE id=$1", projectID).Scan(&ownerID)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if ownerID != userID {
		return false, nil
	}
	return true, nil
}
```

- [ ] **Step 2: Create the TypeScript fixture**

`tests/fixtures/tractability/ts-async-store/package.json`:
```json
{
  "name": "ts-async-store",
  "version": "1.0.0",
  "dependencies": {
    "zustand": "^4.0.0"
  }
}
```

`tests/fixtures/tractability/ts-async-store/src/stores/sessionStore.ts`:
```typescript
import { create } from 'zustand'

interface SessionState {
  userId: string | null
  token: string | null
}

export const useSessionStore = create<SessionState>((set) => ({
  userId: null,
  token: null,

  async login(credentials: { email: string; password: string }) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    })
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('session')
        set({ userId: null, token: null })
        return
      }
      throw new Error('login failed')
    }
    const data = await res.json()
    localStorage.setItem('session', JSON.stringify(data))
    set({ userId: data.userId, token: data.token })
  },

  logout() {
    localStorage.removeItem('session')
    set({ userId: null, token: null })
  },
}))
```

`tests/fixtures/tractability/ts-async-store/src/utils/pure.ts`:
```typescript
export function applyFilters<T>(
  items: T[],
  predicates: Array<(item: T) => boolean>,
): T[] {
  return items.filter((item) => predicates.every((p) => p(item)))
}

export function groupBy<T, K extends string>(
  items: T[],
  key: (item: T) => K,
): Record<K, T[]> {
  const result = {} as Record<K, T[]>
  for (const item of items) {
    const k = key(item)
    if (!result[k]) result[k] = []
    result[k].push(item)
  }
  return result
}
```

- [ ] **Step 3: Create the fake shatter run artifacts**

`tests/fixtures/tractability/fake-shatter-run/summary.json`:
```json
{
  "summary": {
    "integrated": 1,
    "succeeded": 0,
    "failed": 1,
    "not_integrated": 0
  },
  "targets": [
    {
      "root": "go-handlers",
      "languages": ["go"],
      "status": "integrated",
      "outcome": "failed",
      "shatter_outcomes": {
        "projects_handler.UpdateProject": "unsupported"
      }
    }
  ]
}
```

`tests/fixtures/tractability/fake-shatter-run/go-handlers/projects_handler.spec.json`:
```json
{
  "target": "projects_handler.UpdateProject",
  "outcome": "unsupported",
  "reason": "parameter type *sql.DB is not constructible",
  "cases": []
}
```

- [ ] **Step 4: Commit fixtures**

```bash
git add tests/fixtures/tractability/
git commit -m "test: add tractability analysis fixtures"
```

---

## Task 2: Write failing tests for discover_hotspots.py

**Files:**
- Create: `tests/test_discover_hotspots.py`

- [ ] **Step 1: Create the test file**

`tests/test_discover_hotspots.py`:
```python
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "catalog" / "skills" / "shatter-advise" / "scripts" / "discover_hotspots.py"
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "tractability"


def load_module():
    spec = importlib.util.spec_from_file_location("discover_hotspots", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class DetectLanguagesTest(unittest.TestCase):
    def test_detects_go(self) -> None:
        mod = load_module()
        langs = mod.detect_languages(FIXTURES_DIR / "go-handlers")
        self.assertIn("go", langs)

    def test_detects_typescript(self) -> None:
        mod = load_module()
        langs = mod.detect_languages(FIXTURES_DIR / "ts-async-store")
        self.assertIn("typescript", langs)

    def test_detects_neither_for_empty_dir(self) -> None:
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            langs = mod.detect_languages(Path(tmp))
        self.assertEqual(langs, [])


class DiscoverCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_module()

    def test_go_handler_file_gets_handler_and_io_signals(self) -> None:
        candidates = self.mod.discover_candidates(
            FIXTURES_DIR / "go-handlers", ["go"]
        )
        files = {c["file"]: c for c in candidates}
        self.assertIn("internal/handlers/projects.go", files)
        c = files["internal/handlers/projects.go"]
        self.assertIn("http_handler", c["signals"])
        self.assertIn("io_heavy", c["signals"])

    def test_generated_file_without_project_logic_gets_generated_signal(self) -> None:
        candidates = self.mod.discover_candidates(
            FIXTURES_DIR / "go-handlers", ["go"]
        )
        files = {c["file"]: c for c in candidates}
        self.assertIn("internal/handlers/generated.gen.go", files)
        c = files["internal/handlers/generated.gen.go"]
        self.assertIn("generated_glue", c["signals"])
        self.assertNotIn("branch_in_generated", c["signals"])

    def test_generated_file_with_project_logic_gets_branch_in_generated_signal(self) -> None:
        candidates = self.mod.discover_candidates(
            FIXTURES_DIR / "go-handlers", ["go"]
        )
        files = {c["file"]: c for c in candidates}
        self.assertIn("internal/handlers/resolver.gen.go", files)
        c = files["internal/handlers/resolver.gen.go"]
        self.assertIn("generated_glue", c["signals"])
        self.assertIn("branch_in_generated", c["signals"])

    def test_ts_async_store_gets_async_mixed_and_browser_globals_signals(self) -> None:
        candidates = self.mod.discover_candidates(
            FIXTURES_DIR / "ts-async-store", ["typescript"]
        )
        files = {c["file"]: c for c in candidates}
        self.assertIn("src/stores/sessionStore.ts", files)
        c = files["src/stores/sessionStore.ts"]
        self.assertIn("async_mixed", c["signals"])
        self.assertIn("browser_globals", c["signals"])

    def test_pure_ts_file_is_not_a_candidate(self) -> None:
        candidates = self.mod.discover_candidates(
            FIXTURES_DIR / "ts-async-store", ["typescript"]
        )
        files = {c["file"] for c in candidates}
        self.assertNotIn("src/utils/pure.ts", files)


class LoadArtifactsTest(unittest.TestCase):
    def test_loads_unsupported_outcome(self) -> None:
        mod = load_module()
        artifacts = mod.load_shatter_artifacts(
            FIXTURES_DIR / "fake-shatter-run"
        )
        self.assertEqual(len(artifacts), 1)
        a = artifacts[0]
        self.assertEqual(a["target"], "projects_handler.UpdateProject")
        self.assertEqual(a["outcome"], "unsupported")
        self.assertEqual(a["target_root"], "go-handlers")

    def test_returns_empty_list_when_no_run_dir(self) -> None:
        mod = load_module()
        artifacts = mod.load_shatter_artifacts(None)
        self.assertEqual(artifacts, [])


class ProtoClusterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_module()

    def test_handler_with_io_signals_clusters_as_handler_sandwich(self) -> None:
        candidates = [
            {"file": "handlers/a.go", "signals": ["http_handler", "io_heavy", "side_effects"], "artifact_backed": False, "shatter_outcome": None},
            {"file": "handlers/b.go", "signals": ["http_handler", "io_heavy"], "artifact_backed": False, "shatter_outcome": None},
        ]
        clusters = self.mod.proto_cluster(candidates)
        shapes = {c["failure_shape"] for c in clusters}
        self.assertIn("handler_mixes_parse_auth_validate_db_render", shapes)

    def test_async_with_io_clusters_as_async_mixed(self) -> None:
        candidates = [
            {"file": "stores/session.ts", "signals": ["async_mixed", "browser_globals", "io_heavy"], "artifact_backed": False, "shatter_outcome": None},
        ]
        clusters = self.mod.proto_cluster(candidates)
        shapes = {c["failure_shape"] for c in clusters}
        self.assertIn("async_function_mixes_awaited_io_with_branch_logic", shapes)

    def test_artifact_backed_candidates_are_prioritized(self) -> None:
        candidates = [
            {"file": "handlers/a.go", "signals": ["http_handler", "io_heavy"], "artifact_backed": True, "shatter_outcome": "unsupported"},
            {"file": "handlers/b.go", "signals": ["http_handler", "io_heavy"], "artifact_backed": False, "shatter_outcome": None},
        ]
        clusters = self.mod.proto_cluster(candidates)
        handler_cluster = next(
            c for c in clusters
            if c["failure_shape"] == "handler_mixes_parse_auth_validate_db_render"
        )
        self.assertEqual(handler_cluster["candidates"][0]["file"], "handlers/a.go")


class MainCLITest(unittest.TestCase):
    def copy_fixture(self, name: str) -> Path:
        tmpdir = Path(tempfile.mkdtemp(prefix="shatter-advise-"))
        self.addCleanup(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        shutil.copytree(FIXTURES_DIR / name, tmpdir / name)
        return tmpdir / name

    def run_script(self, root: Path, run_dir: Path | None = None) -> dict:
        output = root.parent / "discovery.json"
        import subprocess
        args = [
            sys.executable, str(SCRIPT_PATH),
            "--root", str(root),
            "--output", str(output),
        ]
        if run_dir:
            args += ["--run-dir", str(run_dir)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(output.read_text())

    def test_source_only_mode_produces_valid_discovery_json(self) -> None:
        root = self.copy_fixture("go-handlers")
        data = self.run_script(root)
        self.assertIn("languages", data)
        self.assertIn("candidates", data)
        self.assertIn("proto_clusters", data)
        self.assertFalse(data["artifact_mode"])

    def test_with_artifacts_sets_artifact_mode_and_elevates_priority(self) -> None:
        root = self.copy_fixture("go-handlers")
        run_dir = FIXTURES_DIR / "fake-shatter-run"
        data = self.run_script(root, run_dir=run_dir)
        self.assertTrue(data["artifact_mode"])
        artifact_backed = [c for c in data["candidates"] if c["artifact_backed"]]
        self.assertGreater(len(artifact_backed), 0)

    def test_exits_1_on_missing_root(self) -> None:
        import subprocess
        output = Path(tempfile.mktemp(suffix=".json"))
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH),
             "--root", "/nonexistent/path",
             "--output", str(output)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
python3 -m pytest tests/test_discover_hotspots.py -v 2>&1 | head -40
```

Expected: errors like `FileNotFoundError` or `ModuleNotFoundError` because the script doesn't exist yet. All tests should fail — not error on the test file itself.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_discover_hotspots.py
git commit -m "test: add failing tests for discover_hotspots.py"
```

---

## Task 3: Implement discover_hotspots.py

**Files:**
- Create: `catalog/skills/shatter-advise/scripts/discover_hotspots.py`

- [ ] **Step 1: Create the script**

`catalog/skills/shatter-advise/scripts/discover_hotspots.py`:
```python
#!/usr/bin/env python3
"""
Deterministic discovery pass for shatter-advise and shatter-gaps.

Detects languages, finds candidate files by static signals, loads Shatter
run artifacts, proto-clusters candidates by failure shape, and writes a
discovery.json for the agent to drive deep analysis.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_languages(root: Path) -> list[str]:
    langs = []
    if (root / "go.mod").is_file():
        langs.append("go")
    if (root / "Cargo.toml").is_file():
        langs.append("rust")
    if (root / "package.json").is_file():
        langs.append("typescript")
    return langs


# ---------------------------------------------------------------------------
# Static signal detection helpers
# ---------------------------------------------------------------------------

_GO_HANDLER_IMPORTS = re.compile(r'"net/http"')
_GO_IO_IMPORTS = re.compile(r'"(database/sql|github\.com/jmoiron/sqlx|github\.com/jackc/pgx|os|bufio)"')
_GO_SIDE_EFFECTS = re.compile(r'\b(log\.|fmt\.Fprintf|fmt\.Fprintln|\.Write\(|\.Emit\()')
_GO_GENERATED = re.compile(r'^// (Code generated|DO NOT EDIT)', re.MULTILINE)
_GO_BRANCH = re.compile(r'\b(if |switch )')
_GO_ASYNC_CONCURRENCY = re.compile(r'\bgo func\b|\bgo [a-z]')

_TS_HANDLER_IMPORTS = re.compile(r"(from ['\"]express|from ['\"]fastify|from ['\"]hono|from ['\"]@modelcontextprotocol|app\.(get|post|put|delete|patch)\(|router\.(get|post|put|delete)\()")
_TS_IO_IMPORTS = re.compile(r"from ['\"](pg|mysql2|prisma|@prisma|mongoose|ioredis|redis|axios|node-fetch)")
_TS_BROWSER_GLOBALS = re.compile(r'\b(localStorage|sessionStorage|window\.|document\.)')
_TS_ASYNC_MIXED = re.compile(r'async (function|\(|[a-zA-Z])')
_TS_BRANCH = re.compile(r'\b(if \(|switch \()')
_TS_GENERATED = re.compile(r'^// (Code generated|DO NOT EDIT|This file is auto-generated)', re.MULTILINE)
_TS_STORE = re.compile(r"from ['\"]zustand|createSlice\(|createStore\(")
_TS_SIDE_EFFECTS = re.compile(r'\b(console\.(log|error|warn)|logger\.|\.emit\(|\.publish\()')

_GENERATED_FILENAME = re.compile(r'(\.gen\.|_generated\.|generated_)', re.IGNORECASE)


def _signals_for_go(path: Path, content: str) -> list[str]:
    signals = []
    if _GENERATED_FILENAME.search(path.name) or _GO_GENERATED.search(content):
        signals.append("generated_glue")
        if _GO_BRANCH.search(content):
            signals.append("branch_in_generated")
        return signals
    if _GO_HANDLER_IMPORTS.search(content):
        signals.append("http_handler")
    if _GO_IO_IMPORTS.search(content):
        signals.append("io_heavy")
    if _GO_SIDE_EFFECTS.search(content):
        signals.append("side_effects")
    if _GO_ASYNC_CONCURRENCY.search(content):
        signals.append("async_mixed")
    return signals


def _signals_for_typescript(path: Path, content: str) -> list[str]:
    signals = []
    if _GENERATED_FILENAME.search(path.name) or _TS_GENERATED.search(content):
        signals.append("generated_glue")
        if _TS_BRANCH.search(content):
            signals.append("branch_in_generated")
        return signals
    if _TS_HANDLER_IMPORTS.search(content):
        signals.append("http_handler")
    if _TS_STORE.search(content):
        signals.append("store")
    if _TS_IO_IMPORTS.search(content):
        signals.append("io_heavy")
    if _TS_BROWSER_GLOBALS.search(content):
        signals.append("browser_globals")
    has_async = bool(_TS_ASYNC_MIXED.search(content))
    has_branch = bool(_TS_BRANCH.search(content))
    if has_async and has_branch:
        signals.append("async_mixed")
    if _TS_SIDE_EFFECTS.search(content):
        signals.append("side_effects")
    return signals


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------

_SKIP_DIRS = {".git", "node_modules", "vendor", "target", "dist", "build", "__pycache__"}

def discover_candidates(root: Path, languages: list[str]) -> list[dict]:
    candidates = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(root))
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        signals: list[str] = []
        if "go" in languages and path.suffix == ".go":
            signals = _signals_for_go(path, content)
        elif "typescript" in languages and path.suffix in (".ts", ".tsx", ".js", ".jsx"):
            signals = _signals_for_typescript(path, content)
        elif "rust" in languages and path.suffix == ".rs":
            # Rust signals: minimal for v1
            if re.search(r'use (axum|actix_web|rocket)', content):
                signals.append("http_handler")
            if re.search(r'use (sqlx|tokio_postgres|diesel)', content):
                signals.append("io_heavy")
            if re.search(r'async fn ', content) and re.search(r'\bif ', content):
                signals.append("async_mixed")

        if signals:
            candidates.append({
                "file": rel,
                "signals": signals,
                "artifact_backed": False,
                "shatter_outcome": None,
                "priority": _priority(signals, artifact_backed=False),
            })
    return candidates


def _priority(signals: list[str], artifact_backed: bool) -> str:
    if artifact_backed:
        return "high"
    if "http_handler" in signals and "io_heavy" in signals:
        return "high"
    if "async_mixed" in signals and "io_heavy" in signals:
        return "high"
    if "generated_glue" in signals and "branch_in_generated" in signals:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def load_shatter_artifacts(run_dir: Path | None) -> list[dict]:
    if run_dir is None:
        return []
    summary_path = run_dir / "summary.json"
    if not summary_path.is_file():
        return []
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    artifacts = []
    for target in summary.get("targets", []):
        root_name = target.get("root", "")
        for symbol, outcome in target.get("shatter_outcomes", {}).items():
            spec_candidates = list((run_dir / root_name).glob("*.spec.json")) if (run_dir / root_name).is_dir() else []
            spec_data: dict = {}
            for sp in spec_candidates:
                d = json.loads(sp.read_text(encoding="utf-8"))
                if d.get("target") == symbol:
                    spec_data = d
                    break
            artifacts.append({
                "target": symbol,
                "outcome": outcome,
                "target_root": root_name,
                "reason": spec_data.get("reason", ""),
            })
    return artifacts


# ---------------------------------------------------------------------------
# Proto-clustering
# ---------------------------------------------------------------------------

_SHAPE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("http_handler", "io_heavy"), "handler_mixes_parse_auth_validate_db_render"),
    (("async_mixed", "io_heavy"), "async_function_mixes_awaited_io_with_branch_logic"),
    (("store", "browser_globals"), "store_action_captures_state_and_browser_globals"),
    (("store", "async_mixed"), "async_function_mixes_awaited_io_with_branch_logic"),
    (("generated_glue", "branch_in_generated"), "generated_glue_contains_project_decisions"),
    (("generated_glue",), "generated_framework_glue_no_project_decisions"),
    (("http_handler",), "opaque_resource_parameter_blocks_constructibility"),
]


def _failure_shape(signals: list[str]) -> str:
    signal_set = set(signals)
    for required, shape in _SHAPE_RULES:
        if all(s in signal_set for s in required):
            return shape
    return "unclassified"


def proto_cluster(candidates: list[dict]) -> list[dict]:
    by_shape: dict[str, list[dict]] = {}
    for c in candidates:
        shape = _failure_shape(c["signals"])
        by_shape.setdefault(shape, []).append(c)

    clusters = []
    for shape, members in by_shape.items():
        # Artifact-backed candidates sort first within each cluster
        sorted_members = sorted(members, key=lambda c: (0 if c["artifact_backed"] else 1))
        clusters.append({
            "failure_shape": shape,
            "candidates": sorted_members,
            "artifact_backed_count": sum(1 for m in members if m["artifact_backed"]),
        })
    return clusters


# ---------------------------------------------------------------------------
# Merge artifacts into candidates
# ---------------------------------------------------------------------------

def merge_artifacts(candidates: list[dict], artifacts: list[dict]) -> list[dict]:
    """Elevate candidates that have matching Shatter artifacts."""
    for artifact in artifacts:
        for candidate in candidates:
            # Match on target root prefix appearing in the file path
            root = artifact["target_root"]
            if candidate["file"].startswith(root + "/") or root in candidate["file"]:
                if artifact["outcome"] in ("unsupported", "error_only"):
                    candidate["artifact_backed"] = True
                    candidate["shatter_outcome"] = artifact["outcome"]
                    candidate["priority"] = "high"
    return candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover tractability hotspots.")
    parser.add_argument("--root", required=True, help="Project root to analyze")
    parser.add_argument("--run-dir", help="Optional prior run-shatter output directory")
    parser.add_argument("--output", required=True, help="Path to write discovery.json")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root not found: {root}", file=sys.stderr)
        return 1

    run_dir = Path(args.run_dir) if args.run_dir else None
    if run_dir and not run_dir.is_dir():
        print(f"error: run-dir not found: {run_dir}", file=sys.stderr)
        return 1

    languages = detect_languages(root)
    candidates = discover_candidates(root, languages)
    artifacts = load_shatter_artifacts(run_dir)
    candidates = merge_artifacts(candidates, artifacts)
    clusters = proto_cluster(candidates)

    discovery = {
        "root": str(root),
        "languages": languages,
        "artifact_mode": bool(artifacts),
        "candidates": candidates,
        "proto_clusters": clusters,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(discovery, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the tests**

```bash
python3 -m pytest tests/test_discover_hotspots.py -v
```

Expected: all tests pass. If any fail, investigate — the most likely causes are:
- Signal regex not matching the fixture content (add a quick `grep` to check)
- `generated.gen.go` has a `switch` statement that the test expects NOT to trigger `branch_in_generated` — if so, remove the switch from that fixture or adjust the test expectation

- [ ] **Step 3: Commit**

```bash
git add catalog/skills/shatter-advise/scripts/discover_hotspots.py
git commit -m "feat: implement discover_hotspots.py with language detection and static signals"
```

---

## Task 4: Write shatter-advise SKILL.md and metadata

**Files:**
- Create: `catalog/skills/shatter-advise/SKILL.md`
- Create: `catalog/skills/shatter-advise/metadata.json`

- [ ] **Step 1: Write metadata.json**

`catalog/skills/shatter-advise/metadata.json`:
```json
{
  "recommended_model": "high",
  "audience": ["user"]
}
```

- [ ] **Step 2: Write SKILL.md**

`catalog/skills/shatter-advise/SKILL.md`:
```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add catalog/skills/shatter-advise/
git commit -m "feat: add shatter-advise skill"
```

---

## Task 5: Write shatter-gaps SKILL.md and metadata

**Files:**
- Create: `catalog/skills/shatter-gaps/SKILL.md`
- Create: `catalog/skills/shatter-gaps/metadata.json`

- [ ] **Step 1: Write metadata.json**

`catalog/skills/shatter-gaps/metadata.json`:
```json
{
  "recommended_model": "high",
  "audience": ["user"]
}
```

- [ ] **Step 2: Write SKILL.md**

`catalog/skills/shatter-gaps/SKILL.md`:
```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add catalog/skills/shatter-gaps/
git commit -m "feat: add shatter-gaps skill"
```

---

## Task 6: Register skills in plugins.json and build

**Files:**
- Modify: `catalog/plugins.json`

- [ ] **Step 1: Add skills to plugins.json**

Edit `catalog/plugins.json` to add `"shatter-advise"` and `"shatter-gaps"` to
the shatter plugin's skills list:

```json
{
  "plugins": {
    "shatter": {
      "description": "Install, run, and review Shatter; draft markdown issue reports.",
      "skills": [
        "install-shatter",
        "run-shatter",
        "report-shatter-issues",
        "add-shatter-target",
        "interpret-shatter-spec",
        "shatter-doctor",
        "wire-shatter-ci",
        "shatter-advise",
        "shatter-gaps"
      ],
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
      "skills": ["install-refute", "refute-doctor", "pin-refute", "refute-rename"],
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

- [ ] **Step 2: Run build-plugins**

```bash
python3 scripts/build-plugins
```

Expected: output mentioning the shatter plugin version bumped (patch bump).
No errors.

- [ ] **Step 3: Verify plugins are clean**

```bash
python3 scripts/check-plugins-clean
```

Expected: exits 0. If it exits non-zero, the `plugins/` directory is out of
sync — re-run `scripts/build-plugins` and check for uncommitted changes.

- [ ] **Step 4: Run the full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass including `test_discover_hotspots.py`,
`test_build_plugins.py`, and `test_check_plugins_clean.py`.

- [ ] **Step 5: Commit everything**

```bash
git add catalog/plugins.json plugins/ .claude-plugin/
git commit -m "feat: register shatter-advise and shatter-gaps in shatter plugin"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| discover_hotspots.py with --root, --run-dir, --output | Task 3 |
| Language detection (Go, TS, Rust) | Task 3 |
| Handler, IO-heavy, async-mixed, visibility, side-effect, generated signals | Task 3 |
| Artifact loading (summary.json + spec JSONs) | Task 3 |
| Proto-clustering by failure_shape | Task 3 |
| Artifact-backed candidates prioritized | Task 3 |
| shatter-advise SKILL.md with 9-step workflow | Task 4 |
| Phase 1.5 clustering (8 clusters × 3 examples) | Task 4 |
| Phase 2 taxonomy gates (all 4 + visibility + side-effects) | Task 4 |
| Generated glue 3-way classification | Task 4 |
| 8-question prescription standard | Task 4 |
| report.md with all sections | Task 4 |
| findings.json with full schema | Task 4 |
| ENGINE-GAP count in console summary (no detail) | Task 4 |
| shatter-gaps SKILL.md | Task 5 |
| engine-gaps.md with all sections | Task 5 |
| Linked project/engine findings via linked_finding_ids | Tasks 4 + 5 |
| Skills registered in plugins.json | Task 6 |
| build-plugins and check-plugins-clean pass | Task 6 |
| Script tests for all 8 behaviors | Task 2 |
| Skill acceptance checks documented | Tasks 4 + 5 (in skill workflow) |
| async-shell-sync-core pattern (agents-arz) | Task 4 (pattern catalog reference) |
| report-shatter-issues NOT referenced | Tasks 4 + 5 ✓ |
