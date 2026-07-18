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

# Rust serialization guard: a global `static OnceLock<Mutex<()>>` used to
# serialize tests around shared mutable state (e.g. a function that drains a DB
# table). Shatter's parallel harness execution would violate this invariant
# silently, producing spurious failures or non-deterministic coverage. The
# match is structural on the type signature — not name-based on functions like
# `serial_lock` — and tolerates whitespace and path qualifiers
# (`std::sync::OnceLock<tokio::sync::Mutex<()>>`). `OnceLock<RwLock<()>>` is
# intentionally out of scope.
_RUST_SERIAL_GUARD = re.compile(
    r'static\s+\w+\s*:\s*(?:\w+::)*OnceLock\s*<\s*(?:\w+::)*Mutex\s*<\s*\(\s*\)\s*>\s*>'
)
_SERIAL_GUARD_TYPE = "OnceLock<Mutex<()>>"


# Rust inline-SQL handler: an HTTP entry-point function that embeds a `sqlx`
# query macro directly in its body instead of delegating to a repository/DAO
# function. Such handlers are fat entry points that mix auth/validation with DB
# access — Shatter must drive the whole HTTP stack to reach any branch that is
# really about DB result shapes (empty row, FK violation), and generators must
# reconstruct the full FK chain just to exercise one branch. A repository
# function testing the query in isolation exposes those branches directly, so we
# flag inline-SQL handlers as a shatter-friendliness opportunity.
#
# The distinction from a repository function is structural, not name-based: a
# repo fn takes a bare executor (`&PgPool`, `&mut PgConnection`, `impl
# Executor`) and returns domain types; a handler takes framework extractors
# (axum `State`/`Path`/`Json`/..., actix `web::Data`/`web::Json`/...) or returns
# an HTTP response type (`impl IntoResponse`, `HttpResponse`, `StatusCode`), or
# carries a rocket route attribute. Only `sqlx::query`, `sqlx::query_as`, and
# `sqlx::query_scalar` (qualified or bare-macro form) count as inline SQL.
_RUST_SQLX_CALL = re.compile(
    r'\bsqlx\s*::\s*(query_as|query_scalar|query)\b'
    r'|\b(query_as|query_scalar|query)\s*!'
)
_RUST_HANDLER_EXTRACTOR = re.compile(
    r'\b(State|Path|Query|Json|Form|Extension|TypedHeader|Multipart|ConnectInfo|'
    r'WebSocketUpgrade|RawQuery|OriginalUri)\s*<'
    r'|\bweb\s*::\s*(Path|Query|Json|Form|Data)\b'
    r'|\bHttpRequest\b'
)
_RUST_HANDLER_RETURN = re.compile(
    r'->[^{]*\b(impl\s+IntoResponse|IntoResponse|impl\s+Responder|Responder|'
    r'HttpResponse|Response|StatusCode|Html|Redirect|Json)\b'
)
_RUST_ROCKET_ROUTE = re.compile(
    r'#\[\s*(?:\w+\s*::\s*)*(get|post|put|delete|patch|head|options)\s*\('
)
_RUST_FN_DEF = re.compile(r'\bfn\s+([A-Za-z_]\w*)\s*[(<]')
# A Rust char literal: a unicode escape `'\u{1F600}'`, a byte escape `'\x41'`,
# a simple escape `'\n'`, or a single non-quote char. Matching the full escape
# (rather than `\\.`) keeps the brace of a `\u{...}` escape from being counted
# as code during brace matching. A `'` that matches none of these is a lifetime.
_CHAR_LIT = re.compile(
    r"'(?:\\u\{[0-9a-fA-F_]{1,6}\}|\\x[0-9a-fA-F]{2}|\\.|[^'\\])'"
)


def _strip_rust_literals_and_comments(src: str) -> str:
    """Blank out string/char literals and comments, preserving code and layout.

    Structural analysis (brace matching, signature detection) runs on the result
    so that a `{` inside a SQL string literal or a `sqlx::query` inside a comment
    cannot skew function-body attribution. Blanked spans become spaces (newlines
    preserved); identifiers such as `sqlx::query` are code and survive intact.
    """
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                out.append(' ')
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            depth = 1
            out.append('  ')
            i += 2
            while i < n and depth > 0:
                if src[i] == '/' and i + 1 < n and src[i + 1] == '*':
                    depth += 1
                    out.append('  ')
                    i += 2
                elif src[i] == '*' and i + 1 < n and src[i + 1] == '/':
                    depth -= 1
                    out.append('  ')
                    i += 2
                else:
                    out.append('\n' if src[i] == '\n' else ' ')
                    i += 1
            continue
        if c == 'r' and i + 1 < n and src[i + 1] in '#"':
            j = i + 1
            hashes = 0
            while j < n and src[j] == '#':
                hashes += 1
                j += 1
            if j < n and src[j] == '"':
                closing = '"' + '#' * hashes
                end = src.find(closing, j + 1)
                end = n if end == -1 else end + len(closing)
                for k in range(i, min(end, n)):
                    out.append('\n' if src[k] == '\n' else ' ')
                i = end
                continue
        if c == '"':
            out.append(' ')
            i += 1
            while i < n:
                if src[i] == '\\' and i + 1 < n:
                    out.append('  ')
                    i += 2
                elif src[i] == '"':
                    out.append(' ')
                    i += 1
                    break
                else:
                    out.append('\n' if src[i] == '\n' else ' ')
                    i += 1
            continue
        if c == "'":
            m = _CHAR_LIT.match(src, i)
            if m:
                out.append(' ' * (m.end() - i))
                i = m.end()
                continue
            # Not a char literal (e.g. a lifetime `'a`); leave the quote as code.
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _matching_brace(s: str, open_idx: int) -> int:
    """Return the index of the `}` matching the `{` at `open_idx`.

    Assumes `s` has had literals/comments blanked, so braces are balanced. Falls
    back to end-of-string if no match is found (malformed input).
    """
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return len(s) - 1


def _iter_rust_functions(stripped: str):
    """Yield (name, preamble, signature, body) for each `fn` in blanked source.

    `preamble` is the ~200 chars preceding the fn (for attribute-based handler
    detection); `signature` spans the fn keyword to the body's opening brace;
    `body` is the brace-delimited block.
    """
    for m in _RUST_FN_DEF.finditer(stripped):
        open_idx = stripped.find('{', m.end() - 1)
        if open_idx == -1:
            continue
        # Bodyless declarations (trait method decls, `extern` fns) have no body;
        # their signature ends in `;` before any `{`. Skip them — otherwise the
        # forward `{` search would borrow an unrelated later function's body and
        # attribute it to this declaration's name. A function signature never
        # contains a `;` before its opening brace, so `;` before `{` is decisive.
        semi_idx = stripped.find(';', m.end() - 1)
        if semi_idx != -1 and semi_idx < open_idx:
            continue
        close_idx = _matching_brace(stripped, open_idx)
        yield (
            m.group(1),
            stripped[max(0, m.start() - 200):m.start()],
            stripped[m.start():open_idx],
            stripped[open_idx:close_idx + 1],
        )


def _is_rust_handler(preamble: str, signature: str) -> bool:
    return bool(
        _RUST_HANDLER_EXTRACTOR.search(signature)
        or _RUST_HANDLER_RETURN.search(signature)
        or _RUST_ROCKET_ROUTE.search(preamble)
    )


def _inline_sql_calls(body: str) -> list[str]:
    """Return sorted, de-duplicated `sqlx::`-qualified names of query calls.

    Both the qualified form (`sqlx::query_as::<...>`) and the bare-macro form
    (`query!`, imported via `use sqlx::query`) normalize to the same canonical
    `sqlx::<name>` string.
    """
    calls: set[str] = set()
    for m in _RUST_SQLX_CALL.finditer(body):
        name = m.group(1) or m.group(2)
        calls.add(f"sqlx::{name}")
    return sorted(calls)


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


def detect_serialization_guards(root: Path) -> list[dict]:
    """Scan `.rs` files for a static OnceLock<Mutex<()>> serialization guard.

    Such a guard serializes tests around shared mutable state; Shatter's
    parallel harness execution would violate the invariant silently. The match
    is structural on the type signature (see `_RUST_SERIAL_GUARD`), not on the
    guard function's name. `OnceLock<RwLock<()>>` is intentionally out of scope.
    """
    guards: list[dict] = []
    for path in sorted(root.rglob("*.rs")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Match line-by-line, skipping `//` comment lines, so a commented-out
        # declaration does not produce a spurious guard entry.
        if any(
            not line.lstrip().startswith("//") and _RUST_SERIAL_GUARD.search(line)
            for line in content.splitlines()
        ):
            guards.append({
                "file": str(path.relative_to(root)),
                "guard_type": _SERIAL_GUARD_TYPE,
                "risk": "parallel_harness_serialization",
            })
    return guards


def detect_inline_sql_handlers(root: Path) -> list[dict]:
    """Scan `.rs` files for HTTP handlers that embed a sqlx query inline.

    A handler (entry point identified by framework extractors, an HTTP response
    return type, or a rocket route attribute — see `_is_rust_handler`) whose
    body directly invokes `sqlx::query`, `sqlx::query_as`, or `sqlx::query_scalar`
    is flagged `shatter_friendliness: low` with reason `inline_sql`. Repository
    functions (which take a bare executor and are the recommended target) are not
    handlers, so they are not flagged. See the module comment on `_RUST_SQLX_CALL`.
    """
    findings: list[dict] = []
    for path in sorted(root.rglob("*.rs")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        stripped = _strip_rust_literals_and_comments(content)
        for name, preamble, signature, body in _iter_rust_functions(stripped):
            if not _is_rust_handler(preamble, signature):
                continue
            sql_calls = _inline_sql_calls(body)
            if not sql_calls:
                continue
            findings.append({
                "file": str(path.relative_to(root)),
                "handler": name,
                "shatter_friendliness": "low",
                "reason": "inline_sql",
                "sql_calls": sql_calls,
                "suggestion": (
                    "extract DB access into a repository function so Shatter can "
                    "exercise DB-result-shape branches without driving the full "
                    "HTTP stack"
                ),
            })
    return findings


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
    parser.add_argument(
        "--serialization-guard-policy",
        choices=("warn", "block"),
        default="warn",
        help=(
            "How to treat a detected static OnceLock<Mutex<()>> serialization "
            "guard. 'warn' (default) emits a warning and suggests "
            "single-threaded execution; 'block' records that parallel "
            "execution must be refused for the affected target. Typically "
            "sourced from .shatter/config.yaml."
        ),
    )
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

    serialization_guards = detect_serialization_guards(root)
    policy = args.serialization_guard_policy
    for guard in serialization_guards:
        guard["policy"] = policy
        enforcement = (
            "Config policy is 'block': parallel execution must be refused for "
            "this target."
            if policy == "block"
            else "Warn-only: set the serialization_guard policy to 'block' to "
            "enforce."
        )
        print(
            f"warning: {guard['file']} defines a static {_SERIAL_GUARD_TYPE} "
            "serialization guard. It serializes tests around shared mutable "
            "state; Shatter's parallel harness execution would violate this "
            "invariant silently, producing spurious failures or "
            "non-deterministic coverage. Suggest single-threaded execution "
            f"mode for this target. {enforcement}",
            file=sys.stderr,
        )

    inline_sql_handlers = detect_inline_sql_handlers(root)
    for finding in inline_sql_handlers:
        print(
            f"warning: {finding['file']}:{finding['handler']} embeds SQL inline "
            f"({', '.join(finding['sql_calls'])}). This fat entry point mixes "
            "auth/validation with DB access, so Shatter must drive the full HTTP "
            "stack to reach branches about DB result shapes. Suggest extracting "
            "DB access into a repository function.",
            file=sys.stderr,
        )

    discovery = {
        "root": str(root),
        "languages": languages,
        "artifact_mode": bool(artifacts),
        "candidates": candidates,
        "proto_clusters": clusters,
        "serialization_guards": serialization_guards,
        "serialization_guard_policy": policy,
        "inline_sql_handlers": inline_sql_handlers,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(discovery, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
