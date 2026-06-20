from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_install_md_exists():
    assert (REPO_ROOT / "INSTALL.md").is_file(), "INSTALL.md missing at repo root"


def test_install_md_covers_claude_code():
    text = (REPO_ROOT / "INSTALL.md").read_text()
    assert "extraKnownMarketplaces" in text, "INSTALL.md missing Claude Code marketplace config"
    assert "shatterproof" in text


def test_install_md_covers_codex():
    text = (REPO_ROOT / "INSTALL.md").read_text()
    assert "codex-home.sh" in text, "INSTALL.md missing Codex curl install command"
    assert "codex plugin add" in text, "INSTALL.md missing codex plugin add step"


def test_installing_plugins_md_includes_plugin_add_step():
    text = (REPO_ROOT / "docs" / "installing-plugins.md").read_text()
    assert "codex plugin add" in text, (
        "docs/installing-plugins.md is missing the 'codex plugin add' step"
    )


def test_readme_links_to_install_md():
    text = (REPO_ROOT / "README.md").read_text()
    assert "INSTALL.md" in text, "README.md does not link to INSTALL.md"
