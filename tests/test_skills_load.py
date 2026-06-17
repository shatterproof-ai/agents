from __future__ import annotations

import json
import re
import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "catalog" / "skills"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _all_skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_skill_has_valid_frontmatter(skill_dir: Path):
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file(), f"{skill_md} missing"
    m = FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    assert m, f"{skill_md} missing frontmatter"
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    assert fm["name"] == skill_dir.name
    assert "description" in fm and fm["description"]
    assert set(fm) == {"name", "description"}, f"extra keys: {set(fm) - {'name','description'}}"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_skill_metadata_parses(skill_dir: Path):
    metadata = skill_dir / "metadata.json"
    assert metadata.is_file(), f"{metadata} missing"
    data = json.loads(metadata.read_text(encoding="utf-8"))
    assert data.get("recommended_model") in {"low", "mid", "high"}, f"bad recommended_model in {metadata}"


@pytest.mark.parametrize("skill_dir", _all_skill_dirs(), ids=lambda p: p.name)
def test_skill_companion_scripts_are_executable(skill_dir: Path):
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        pytest.skip("no scripts/ directory")
    for script in scripts_dir.iterdir():
        if script.is_file():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script} is not executable"
