#!/usr/bin/env python3
"""Run integrated Shatter wrappers across all discovered targets."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO


SUPPORTED_MARKERS = {
    "Cargo.toml": "rust",
    "go.mod": "go",
    "package.json": "typescript",
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".turbo",
    ".venv",
    ".yarn",
    "__pycache__",
    "__fixtures__",
    "build",
    "coverage",
    "dist",
    "fixtures",
    "node_modules",
    "out",
    "target",
    "testdata",
    "tmp",
    "vendor",
}

TASK_SHATTER_PATTERN = re.compile(r"(?m)^[ \t]{2,}shatter:\s*$")


@dataclass(frozen=True)
class Target:
    root: str
    languages: list[str]
    markers: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run project-defined Shatter wrappers for all integrated targets.",
    )
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    parser.add_argument(
        "--run-dir",
        help="Directory for run artifacts. Defaults to shatter-review/<timestamp> under the repo root.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON instead of a human summary.",
    )
    return parser.parse_args()


def should_exclude_dir(name: str) -> bool:
    if name in EXCLUDED_DIR_NAMES:
        return True
    if name.startswith(".") and name not in {".shatter"}:
        return True
    return False


def repo_relpath(path: Path, repo_root: Path) -> str:
    relative = os.path.relpath(path, repo_root).replace(os.sep, "/")
    return "." if relative == "." else relative


def discover_targets(repo_root: Path) -> list[Target]:
    targets: list[Target] = []
    for current_root, dir_names, file_names in os.walk(repo_root, topdown=True):
        current = Path(current_root)
        dir_names[:] = [name for name in sorted(dir_names) if not should_exclude_dir(name)]
        markers = [marker for marker in sorted(SUPPORTED_MARKERS) if marker in file_names]
        if not markers:
            continue
        targets.append(
            Target(
                root=repo_relpath(current, repo_root),
                languages=sorted({SUPPORTED_MARKERS[marker] for marker in markers}),
                markers=markers,
            )
        )
    targets.sort(key=lambda target: (target.root != ".", target.root))
    return targets


def load_package_json(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def package_manager_command(target_path: Path, package_data: dict[str, object]) -> list[str]:
    package_manager = package_data.get("packageManager")
    if isinstance(package_manager, str):
        name = package_manager.split("@", 1)[0].lower()
        if name == "pnpm":
            return ["pnpm", "run", "shatter"]
        if name == "yarn":
            return ["yarn", "shatter"]
        if name == "bun":
            return ["bun", "run", "shatter"]
        if name == "npm":
            return ["npm", "run", "shatter"]

    if (target_path / "pnpm-lock.yaml").is_file():
        return ["pnpm", "run", "shatter"]
    if (target_path / "yarn.lock").is_file():
        return ["yarn", "shatter"]
    if (target_path / "bun.lock").is_file() or (target_path / "bun.lockb").is_file():
        return ["bun", "run", "shatter"]
    return ["npm", "run", "shatter"]


def detect_integration(target: Target, repo_root: Path) -> dict[str, object]:
    target_path = repo_root if target.root == "." else repo_root / target.root

    package_json = target_path / "package.json"
    if package_json.is_file():
        package_data = load_package_json(package_json)
        scripts = package_data.get("scripts") if isinstance(package_data, dict) else None
        if isinstance(scripts, dict) and isinstance(scripts.get("shatter"), str):
            return {
                "status": "integrated",
                "reason": "local package.json script",
                "surface": {
                    "type": "package-json-scripts",
                    "path": repo_relpath(package_json, repo_root),
                },
                "wrapper_command": scripts["shatter"],
                "invocation": package_manager_command(target_path, package_data),
                "cwd": target.root,
            }

    taskfile = target_path / "Taskfile.yml"
    if taskfile.is_file():
        try:
            content = taskfile.read_text(encoding="utf-8")
        except OSError:
            content = ""
        if TASK_SHATTER_PATTERN.search(content):
            task_runner = ["task", "shatter"] if shutil.which("task") else ["npx", "task", "shatter"]
            return {
                "status": "integrated",
                "reason": "local Taskfile task",
                "surface": {
                    "type": "taskfile",
                    "path": repo_relpath(taskfile, repo_root),
                },
                "wrapper_command": "task shatter",
                "invocation": task_runner,
                "cwd": target.root,
            }

    return {
        "status": "not_integrated",
        "reason": "no local shatter wrapper command",
        "surface": None,
        "wrapper_command": None,
        "invocation": None,
        "cwd": target.root,
    }


def discover_integrated_targets(repo_root: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for target in discover_targets(repo_root):
        results.append(
            {
                "root": target.root,
                "languages": target.languages,
                "markers": target.markers,
                **detect_integration(target, repo_root),
            }
        )
    return results


def sanitize_name(root: str) -> str:
    if root == ".":
        return "repo-root"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", root)


def default_run_dir(repo_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return repo_root / "shatter-review" / timestamp


def target_artifact_paths(run_dir: Path, root: str) -> dict[str, Path]:
    target_dir = run_dir / sanitize_name(root)
    return {
        "dir": target_dir,
        "stdout": target_dir / "stdout.txt",
        "stderr": target_dir / "stderr.txt",
        "command": target_dir / "command.json",
        "result": target_dir / "result.json",
    }


def emit(stream: TextIO | None, message: str) -> None:
    if stream is None:
        return
    stream.write(f"{message}\n")
    stream.flush()


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def execute_targets(
    repo_root: Path,
    targets: list[dict[str, object]],
    run_dir: Path,
    stream: TextIO | None = None,
    command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    summary = {
        "total": len(targets),
        "integrated": 0,
        "succeeded": 0,
        "failed": 0,
        "not_integrated": 0,
    }

    for target in targets:
        paths = target_artifact_paths(run_dir, str(target["root"]))
        paths["dir"].mkdir(parents=True, exist_ok=True)

        result = {
            "root": target["root"],
            "languages": target["languages"],
            "markers": target["markers"],
            "status": target["status"],
            "reason": target["reason"],
            "surface": target["surface"],
            "wrapper_command": target["wrapper_command"],
            "invocation": target["invocation"],
            "cwd": target["cwd"],
            "artifact_dir": repo_relpath(paths["dir"], repo_root),
        }

        if target["status"] != "integrated":
            summary["not_integrated"] += 1
            result["outcome"] = "not_integrated"
            write_json(paths["result"], result)
            results.append(result)
            emit(stream, f"[not integrated] {target['root']}: {target['reason']}")
            continue

        summary["integrated"] += 1
        cwd = repo_root if target["cwd"] == "." else repo_root / str(target["cwd"])
        command = [str(part) for part in target["invocation"]]
        emit(stream, f"[running] {target['root']}: {' '.join(command)}")
        proc = command_runner(command, cwd)

        paths["stdout"].write_text(proc.stdout, encoding="utf-8")
        paths["stderr"].write_text(proc.stderr, encoding="utf-8")
        write_json(
            paths["command"],
            {
                "cwd": str(cwd),
                "command": command,
                "wrapper_command": target["wrapper_command"],
            },
        )

        result["exit_code"] = proc.returncode
        result["stdout_path"] = repo_relpath(paths["stdout"], repo_root)
        result["stderr_path"] = repo_relpath(paths["stderr"], repo_root)
        result["command_path"] = repo_relpath(paths["command"], repo_root)
        if proc.returncode == 0:
            summary["succeeded"] += 1
            result["outcome"] = "succeeded"
            emit(stream, f"[ok] {target['root']}")
        else:
            summary["failed"] += 1
            result["outcome"] = "failed"
            emit(stream, f"[failed] {target['root']}: exit {proc.returncode}")
            if proc.stderr.strip():
                emit(stream, proc.stderr.strip())
            elif proc.stdout.strip():
                emit(stream, proc.stdout.strip())

        write_json(paths["result"], result)
        results.append(result)

    payload = {
        "repo_root": str(repo_root.resolve()),
        "run_dir": str(run_dir.resolve()),
        "targets": results,
        "summary": summary,
    }
    write_json(run_dir / "summary.json", payload)
    return payload


def print_human_summary(payload: dict[str, object]) -> None:
    summary = payload["summary"]
    print(f"Run dir: {payload['run_dir']}")
    print(
        "Summary:"
        f" total={summary['total']}"
        f" integrated={summary['integrated']}"
        f" succeeded={summary['succeeded']}"
        f" failed={summary['failed']}"
        f" not_integrated={summary['not_integrated']}"
    )
    for target in payload["targets"]:
        print(
            f"- {target['root']}: {target['outcome']}"
            f" ({target['reason']})"
        )


def main() -> int:
    args = parse_args()
    repo_root = Path(args.root).resolve()
    run_dir = Path(args.run_dir).resolve() if args.run_dir else default_run_dir(repo_root)
    targets = discover_integrated_targets(repo_root)
    payload = execute_targets(repo_root, targets, run_dir, stream=sys.stderr if args.json else sys.stdout)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human_summary(payload)
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
