from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "catalog" / "skills" / "run-shatter" / "scripts" / "run_targets.py"
)
SPEC = importlib.util.spec_from_file_location("run_targets", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "run-targets"


class RunTargetsTest(unittest.TestCase):
    def copy_fixture(self, name: str) -> Path:
        tempdir = Path(tempfile.mkdtemp(prefix="shatter-run-targets-"))
        self.addCleanup(lambda: shutil.rmtree(tempdir, ignore_errors=True))
        shutil.copytree(FIXTURES_DIR / name, tempdir / name)
        return tempdir / name

    def test_discovers_integrated_and_not_integrated_targets(self) -> None:
        repo = self.copy_fixture("mixed-repo")

        targets = {target["root"]: target for target in MODULE.discover_integrated_targets(repo)}

        self.assertEqual(set(targets), {"go-service", "rust-lib", "ts-app"})
        self.assertEqual(targets["ts-app"]["status"], "integrated")
        self.assertEqual(targets["ts-app"]["surface"]["type"], "package-json-scripts")
        self.assertEqual(targets["ts-app"]["invocation"], ["npm", "run", "shatter"])
        self.assertEqual(targets["go-service"]["status"], "integrated")
        self.assertEqual(targets["go-service"]["surface"]["type"], "taskfile")
        self.assertEqual(targets["rust-lib"]["status"], "not_integrated")

    def test_prefers_pnpm_when_package_manager_declares_it(self) -> None:
        repo = self.copy_fixture("pnpm-repo")

        target = MODULE.discover_integrated_targets(repo)[0]
        self.assertEqual(target["invocation"], ["pnpm", "run", "shatter"])

    def test_runs_integrated_targets_and_continues_after_failure(self) -> None:
        repo = self.copy_fixture("mixed-repo")
        run_dir = repo / "artifacts"
        targets = MODULE.discover_integrated_targets(repo)

        def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            if cwd.name == "ts-app":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="ts ok\n",
                    stderr="",
                )
            if cwd.name == "go-service":
                return subprocess.CompletedProcess(
                    command,
                    7,
                    stdout="",
                    stderr="go failed\n",
                )
            raise AssertionError(f"unexpected cwd: {cwd}")

        payload = MODULE.execute_targets(repo, targets, run_dir, stream=None, command_runner=fake_runner)

        self.assertEqual(payload["summary"]["integrated"], 2)
        self.assertEqual(payload["summary"]["succeeded"], 1)
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual(payload["summary"]["not_integrated"], 1)

        by_root = {target["root"]: target for target in payload["targets"]}
        self.assertEqual(by_root["ts-app"]["outcome"], "succeeded")
        self.assertEqual(by_root["go-service"]["outcome"], "failed")
        self.assertEqual(by_root["rust-lib"]["outcome"], "not_integrated")

        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["summary"]["failed"], 1)
        self.assertTrue((run_dir / "ts-app" / "stdout.txt").is_file())
        self.assertTrue((run_dir / "go-service" / "stderr.txt").is_file())
        self.assertTrue((run_dir / "rust-lib" / "result.json").is_file())


if __name__ == "__main__":
    unittest.main()
