from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD = REPO_ROOT / "scripts" / "build-plugins"


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(f.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def test_double_build_produces_zero_diff(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    for top in ("catalog", "scripts"):
        shutil.copytree(REPO_ROOT / top, work / top, symlinks=True)
    subprocess.run([str(BUILD), "--output-root", str(work)], check=True)
    h1 = _hash_tree(work / "plugins")
    v1 = (work / "catalog" / "plugin-versions.json").read_text(encoding="utf-8")
    subprocess.run([str(BUILD), "--output-root", str(work)], check=True)
    h2 = _hash_tree(work / "plugins")
    v2 = (work / "catalog" / "plugin-versions.json").read_text(encoding="utf-8")
    assert h1 == h2
    assert v1 == v2
