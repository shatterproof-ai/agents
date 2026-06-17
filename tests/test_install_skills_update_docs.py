from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "skills"

# Each install skill ships its own copy of the helper; a tool's tests must
# exercise that tool's copy so drift in one copy cannot hide behind the other.
HELPERS = {
    "refute": _CATALOG / "install-refute" / "scripts" / "update_usage_stanza.py",
    "shatter": _CATALOG / "install-shatter" / "scripts" / "update_usage_stanza.py",
}


def _run_helper(project_root: Path, tool: str, *extra: str) -> None:
    subprocess.run(
        [sys.executable, str(HELPERS[tool]), "--tool", tool, "--project-root", str(project_root), *extra],
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


def test_shatter_stanza_inserts_when_absent(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n\nExisting.\n", encoding="utf-8")
    _run_helper(tmp_path, "shatter", "--version", "0.2.0", "--backend", "gopls")
    contents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- shatter:usage -->" in contents
    assert "<!-- /shatter:usage -->" in contents
    assert "Existing." in contents
    assert "`gopls`" in contents


def test_shatter_marker_names_are_correct(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    _run_helper(tmp_path, "shatter")
    contents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- shatter:usage -->" in contents
    assert "<!-- /shatter:usage -->" in contents
    assert "## Shatter Usage" in contents


def test_install_helpers_are_byte_identical():
    refute = HELPERS["refute"].read_bytes()
    shatter = HELPERS["shatter"].read_bytes()
    assert refute == shatter


def test_shatter_rerun_is_idempotent(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    _run_helper(tmp_path, "shatter", "--version", "0.2.0")
    first = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert first.count("<!-- shatter:usage -->") == 1
    _run_helper(tmp_path, "shatter", "--version", "0.2.0")
    second = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
    assert second.count("<!-- shatter:usage -->") == 1


def test_shatter_stanza_updates_existing(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    _run_helper(tmp_path, "shatter", "--version", "0.2.0")
    _run_helper(tmp_path, "shatter", "--version", "0.3.0")
    contents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert contents.count("<!-- shatter:usage -->") == 1
    assert "`0.3.0`" in contents
    assert "`0.2.0`" not in contents


def test_shatter_creates_docs_and_readme_when_neither_exists(tmp_path):
    _run_helper(tmp_path, "shatter", "--version", "0.2.0")
    assert (tmp_path / "docs" / "shatter-usage.md").is_file()
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "<!-- shatter:pointer -->" in readme
    assert "docs/shatter-usage.md" in readme
