from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build-plugins"


def _load_build():
    spec = importlib.util.spec_from_loader(
        "build_plugins",
        importlib.machinery.SourceFileLoader("build_plugins", str(SCRIPT)),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_skill_with_overlay(tmp_path: Path, body: str, overlay_name: str, overlay_text: str) -> Path:
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\n---\n\n" + body + "\n", encoding="utf-8"
    )
    (skill / "metadata.json").write_text("{}\n", encoding="utf-8")
    (skill / overlay_name).write_text(overlay_text, encoding="utf-8")
    return skill


def test_overlay_with_frontmatter_is_rejected(tmp_path):
    build = _load_build()
    _write_skill_with_overlay(tmp_path, "body", "CLAUDE.md", "---\nx: y\n---\n## hi\n")
    with pytest.raises(build.BuildError, match="must not contain frontmatter"):
        build.load_skill(tmp_path / "skills" / "demo")


def test_overlay_must_start_with_h2(tmp_path):
    build = _load_build()
    _write_skill_with_overlay(tmp_path, "body", "CLAUDE.md", "no heading here\n")
    with pytest.raises(build.BuildError, match="level-2 heading"):
        build.load_skill(tmp_path / "skills" / "demo")


def test_composed_skill_has_base_then_overlay(tmp_path):
    build = _load_build()
    _write_skill_with_overlay(tmp_path, "base body", "CLAUDE.md", "## Claude only\nextra\n")
    skill = build.load_skill(tmp_path / "skills" / "demo")
    composed = build.compose_skill(skill, "claude")
    assert composed.index("base body") < composed.index("## Claude only")
    plain = build.compose_skill(skill, "codex")
    assert "## Claude only" not in plain
