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

_SKIP_DIRS = {".git", ".shatter", "node_modules", "vendor", "target", "dist", "build", "__pycache__"}

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
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"warning: could not parse {summary_path}: {e}", file=sys.stderr)
        return []
    artifacts = []
    for target in summary.get("targets", []):
        root_name = target.get("root", "")
        for symbol, outcome in target.get("shatter_outcomes", {}).items():
            spec_candidates = list((run_dir / root_name).glob("*.spec.json")) if (run_dir / root_name).is_dir() else []
            spec_data: dict = {}
            for sp in spec_candidates:
                try:
                    d = json.loads(sp.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    print(f"warning: could not parse {sp}: {e}", file=sys.stderr)
                    continue
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

def merge_artifacts(candidates: list[dict], artifacts: list[dict], root: Path | None = None) -> list[dict]:
    """Elevate candidates that have matching Shatter artifacts."""
    root_name = root.name if root is not None else None
    for artifact in artifacts:
        artifact_root = artifact["target_root"]
        # Match if: (1) the project root directory name equals target_root, meaning
        # all candidates in this root are relevant; or (2) candidate file path
        # starts with target_root/ (for multi-project monorepo layouts).
        root_matches_project = root_name is not None and artifact_root == root_name
        for candidate in candidates:
            file_path = candidate["file"]
            path_matches = file_path.startswith(artifact_root + "/") or f"/{artifact_root}/" in f"/{file_path}"
            if root_matches_project or path_matches:
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
    candidates = merge_artifacts(candidates, artifacts, root=root)
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
