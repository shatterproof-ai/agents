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


def test_compute_plugin_hash_is_deterministic(tmp_path):
    build = _load_build_module()
    a = tmp_path / "a" ; b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "skill.md").write_text("body\n", encoding="utf-8")
        (d / "extra.json").write_text("{}\n", encoding="utf-8")
    assert build.compute_plugin_hash(a) == build.compute_plugin_hash(b)


def test_compute_plugin_hash_changes_on_content_change(tmp_path):
    build = _load_build_module()
    d = tmp_path / "p" ; d.mkdir()
    (d / "f.txt").write_text("one", encoding="utf-8")
    first = build.compute_plugin_hash(d)
    (d / "f.txt").write_text("two", encoding="utf-8")
    assert build.compute_plugin_hash(d) != first


def test_bump_version_if_changed_bumps_patch_on_hash_mismatch():
    build = _load_build_module()
    versions = {"shatter": {"version": "1.2.3", "content_hash": "old"}}
    bumped = build.bump_version_if_changed(versions, "shatter", "new")
    assert bumped == "1.2.4"
    assert versions["shatter"] == {"version": "1.2.4", "content_hash": "new"}


def test_bump_version_if_changed_noop_when_hash_matches():
    build = _load_build_module()
    versions = {"shatter": {"version": "1.2.3", "content_hash": "same"}}
    bumped = build.bump_version_if_changed(versions, "shatter", "same")
    assert bumped == "1.2.3"
    assert versions["shatter"]["version"] == "1.2.3"


def test_bump_version_consumes_patch_zero_anchor():
    """Patch=0 is the manual-bump anchor. First content change after a
    manual major/minor bump bumps patch to 1 (consuming the anchor) so
    subsequent changes resume normal auto-bumping."""
    build = _load_build_module()
    versions = {"shatter": {"version": "2.0.0", "content_hash": "old"}}
    bumped = build.bump_version_if_changed(versions, "shatter", "new")
    assert bumped == "2.0.1"
    assert versions["shatter"]["content_hash"] == "new"


def test_bump_version_initial_entry_bumps_to_patch_one():
    """A fresh plugin-versions.json entry (empty hash, patch=0) bumps
    to patch=1 on the first build, consuming the anchor."""
    build = _load_build_module()
    versions = {"shatter": {"version": "0.1.0", "content_hash": ""}}
    bumped = build.bump_version_if_changed(versions, "shatter", "first")
    assert bumped == "0.1.1"
    assert versions["shatter"]["content_hash"] == "first"


def test_write_plugin_manifests_writes_claude_and_codex(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    cat = build.load_catalog(catalog)
    out = tmp_path / "out"
    (out / "claude" / "greetings").mkdir(parents=True)
    (out / "codex" / "greetings").mkdir(parents=True)
    build.write_plugin_manifests(cat.plugins["greetings"], "9.9.9", out)
    claude = json.loads((out / "claude" / "greetings" / ".claude-plugin" / "plugin.json").read_text())
    codex  = json.loads((out / "codex"  / "greetings" / ".codex-plugin"  / "plugin.json").read_text())
    assert claude["version"] == "9.9.9"
    assert claude["author"] == {"name": "X"}
    assert codex["version"] == "9.9.9"
    assert codex["interface"]["displayName"] == "Greetings"


def test_build_all_end_to_end(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    out = tmp_path / "repo"
    out.mkdir()
    (out / "catalog").symlink_to(catalog)
    build.build_all(out)
    assert (out / "plugins" / "claude" / "greetings" / "skills" / "hello" / "SKILL.md").is_file()
    assert (out / "plugins" / "codex"  / "greetings" / "skills" / "hello" / "SKILL.md").is_file()
    mp = json.loads((out / ".claude-plugin" / "marketplace.json").read_text())
    assert mp["plugins"][0]["name"] == "greetings"
    assert mp["plugins"][0]["source"] == "./plugins/claude/greetings"
    versions = json.loads((catalog / "plugin-versions.json").read_text())
    assert versions["greetings"]["version"] == "0.1.1"   # patch=0 anchor consumed; first build bumps to 0.1.1
    assert versions["greetings"]["content_hash"] != ""


def test_build_all_is_idempotent(tmp_path):
    build = _load_build_module()
    catalog = _make_catalog(tmp_path)
    out = tmp_path / "repo"
    out.mkdir()
    (out / "catalog").symlink_to(catalog)
    build.build_all(out)
    snap1 = sorted(p.relative_to(out).as_posix() for p in (out / "plugins").rglob("*") if p.is_file())
    hash1 = json.loads((catalog / "plugin-versions.json").read_text())["greetings"]["content_hash"]
    build.build_all(out)
    snap2 = sorted(p.relative_to(out).as_posix() for p in (out / "plugins").rglob("*") if p.is_file())
    hash2 = json.loads((catalog / "plugin-versions.json").read_text())["greetings"]["content_hash"]
    assert snap1 == snap2
    assert hash1 == hash2
