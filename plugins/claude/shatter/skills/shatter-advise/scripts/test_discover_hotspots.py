#!/usr/bin/env python3
"""Tests for discover_hotspots.py.

Run with: python3 test_discover_hotspots.py
(No third-party dependencies; uses assertions and a temp dir.)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from discover_hotspots import detect_serialization_guards


def _guards_for(source: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "lib.rs").write_text(source, encoding="utf-8")
        return detect_serialization_guards(root)


def test_active_guard_is_detected() -> None:
    guards = _guards_for("static M: OnceLock<Mutex<()>> = OnceLock::new();\n")
    assert len(guards) == 1, guards
    assert guards[0]["guard_type"] == "OnceLock<Mutex<()>>"


def test_qualified_path_guard_is_detected() -> None:
    guards = _guards_for(
        "static M: std::sync::OnceLock<tokio::sync::Mutex<()>> = "
        "std::sync::OnceLock::new();\n"
    )
    assert len(guards) == 1, guards


def test_commented_out_guard_is_ignored() -> None:
    guards = _guards_for("// static M: OnceLock<Mutex<()>> = OnceLock::new();\n")
    assert guards == [], guards


def test_indented_commented_out_guard_is_ignored() -> None:
    guards = _guards_for("    // static M: OnceLock<Mutex<()>> = OnceLock::new();\n")
    assert guards == [], guards


def test_active_guard_among_comments_is_detected() -> None:
    source = (
        "// old approach below, kept for reference:\n"
        "// static OLD: OnceLock<Mutex<()>> = OnceLock::new();\n"
        "static M: OnceLock<Mutex<()>> = OnceLock::new();\n"
    )
    guards = _guards_for(source)
    assert len(guards) == 1, guards


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok - {t.__name__}")
    print(f"\n{len(tests)} passed")
