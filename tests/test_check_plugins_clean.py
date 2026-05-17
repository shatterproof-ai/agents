from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-plugins-clean"


def test_check_plugins_clean_exits_zero_when_in_sync():
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_plugins_clean_fails_when_drift_introduced(tmp_path):
    # Copy the working tree minimally — only catalog/, plugins/, scripts/, .claude-plugin/
    import shutil
    for top in ("catalog", "plugins", "scripts", ".claude-plugin"):
        src = REPO_ROOT / top
        if src.exists():
            shutil.copytree(src, tmp_path / top, symlinks=True)
    # Introduce drift: edit a generated file
    target = tmp_path / "plugins" / "claude" / "shatter" / "skills" / "install-shatter" / "SKILL.md"
    target.write_text("drift!\n", encoding="utf-8")
    result = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert result.returncode != 0
    assert "drift" in (result.stdout + result.stderr).lower() or "differ" in (result.stdout + result.stderr).lower()
