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
