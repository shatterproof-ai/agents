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
