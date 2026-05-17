from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build-plugins"


def _load_build_module():
    spec = importlib.util.spec_from_loader(
        "build_plugins",
        importlib.machinery.SourceFileLoader("build_plugins", str(SCRIPT_PATH)),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_main_returns_zero():
    build = _load_build_module()
    assert build.main([]) == 0


import json
import pytest


def _make_catalog(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog"
    (catalog / "skills" / "hello").mkdir(parents=True)
    (catalog / "skills" / "hello" / "SKILL.md").write_text(
        "---\nname: hello\ndescription: Greet the world.\n---\n\nHi.\n",
        encoding="utf-8",
    )
    (catalog / "skills" / "hello" / "metadata.json").write_text(
        '{"recommended_model": "low"}\n', encoding="utf-8"
    )
    (catalog / "plugins.json").write_text(json.dumps({
        "plugins": {
            "greetings": {
                "description": "Greet things.",
                "skills": ["hello"],
                "claude": {"author": "X"},
                "codex": {"interface": {"displayName": "Greetings"}},
            }
        }
    }), encoding="utf-8")
    (catalog / "plugin-versions.json").write_text(
        '{"greetings": {"version": "0.1.0", "content_hash": ""}}\n',
        encoding="utf-8",
    )
    return catalog


def test_load_catalog_returns_plugins_and_skills(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    loaded = build.load_catalog(catalog)
    assert list(loaded.plugins) == ["greetings"]
    assert loaded.plugins["greetings"].skills == ["hello"]
    assert "hello" in loaded.skills
    assert loaded.skills["hello"].frontmatter["name"] == "hello"
    assert loaded.skills["hello"].metadata == {"recommended_model": "low"}


def test_parse_frontmatter_rejects_extra_keys():
    build = _load_build_module()
    bad = "---\nname: x\ndescription: y\nrecommended_model: low\n---\n\nbody\n"
    with pytest.raises(build.BuildError, match="extra frontmatter key"):
        build.parse_frontmatter(bad, source="x/SKILL.md")


def test_compose_skill_appends_overlay(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    (catalog / "skills" / "hello" / "CLAUDE.md").write_text(
        "## Claude-only\nspecific\n", encoding="utf-8"
    )
    cat = build.load_catalog(catalog)
    composed = build.compose_skill(cat.skills["hello"], "claude")
    assert composed.startswith("---\nname: hello\ndescription: Greet the world.\n---\n")
    assert "## Claude-only\nspecific" in composed
    assert composed.index("Hi.") < composed.index("## Claude-only")


def test_compose_skill_no_overlay_returns_base(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    cat = build.load_catalog(catalog)
    composed = build.compose_skill(cat.skills["hello"], "codex")
    assert composed.endswith("Hi.\n") or composed.endswith("Hi.")
    assert "## " not in composed.split("---\n", 2)[-1].split("\n", 1)[0]


def test_write_skill_copies_companions(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    (catalog / "skills" / "hello" / "scripts").mkdir()
    helper = catalog / "skills" / "hello" / "scripts" / "say.sh"
    helper.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    helper.chmod(0o755)
    cat = build.load_catalog(catalog)
    out = tmp_path / "out"
    build.write_skill(cat.skills["hello"], "claude", out / "skills" / "hello")
    assert (out / "skills" / "hello" / "SKILL.md").is_file()
    assert (out / "skills" / "hello" / "metadata.json").is_file()
    copied = out / "skills" / "hello" / "scripts" / "say.sh"
    assert copied.is_file()
    assert copied.stat().st_mode & 0o111  # exec bits preserved
