from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


BOOTSTRAP = Path(__file__).resolve().parents[1] / "install" / "codex-home.sh"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install-codex-plugins"


def create_generated_plugin(root: Path, name: str, *, category: str = "Developer Tools") -> None:
    plugin_root = root / "plugins" / "codex" / name
    skill_root = plugin_root / "skills" / f"install-{name}"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        f"---\nname: install-{name}\ndescription: Install {name}.\n---\n\nInstall.\n",
        encoding="utf-8",
    )
    manifest_dir = plugin_root / ".codex-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "0.1.0",
                "description": f"{name} plugin",
                "skills": "./skills/",
                "interface": {"displayName": name.title(), "category": category},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def run_installer(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def run_bootstrap(source: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SHATTER_AGENTS_SOURCE": str(source),
        "CODEX_HOME": str(source / ".codex"),
    }
    command = [str(BOOTSTRAP), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env)


def test_help_flag_succeeds() -> None:
    result = run_installer("--help")

    assert result.returncode == 0
    assert "Install generated shatterproof Codex plugins" in result.stdout
    assert "--marketplace-root" in result.stdout


def test_bootstrap_help_flag_succeeds() -> None:
    result = subprocess.run([str(BOOTSTRAP), "--help"], capture_output=True, text=True, check=False)

    assert result.returncode == 0
    assert "curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter-agents/main/install/codex-home.sh | bash" in result.stdout
    assert "Options are forwarded to scripts/install-codex-plugins" in result.stdout


def test_dry_run_does_not_write_marketplace(tmp_path: Path) -> None:
    source = tmp_path / "source"
    create_generated_plugin(source, "shatter")
    marketplace = tmp_path / "marketplace"

    result = run_installer(
        "--source",
        str(source),
        "--marketplace-root",
        str(marketplace),
        "--skip-register",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "Would install shatterproof Codex plugins" in result.stdout
    assert "Plugins: shatter" in result.stdout
    assert not marketplace.exists()


def test_bootstrap_uses_existing_source_without_network(tmp_path: Path) -> None:
    source = tmp_path / "source"
    create_generated_plugin(source, "shatter")
    (source / "scripts").mkdir()
    shutil.copy2(SCRIPT, source / "scripts" / "install-codex-plugins")
    marketplace = tmp_path / "marketplace"

    result = run_bootstrap(
        source,
        "--marketplace-root",
        str(marketplace),
        "--skip-register",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "Would install shatterproof Codex plugins" in result.stdout
    assert f"Source: {source}" in result.stdout
    assert "Plugins: shatter" in result.stdout
    assert not marketplace.exists()


def test_installer_writes_local_marketplace_from_generated_codex_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    create_generated_plugin(source, "shatter")
    create_generated_plugin(source, "refute", category="Coding")
    marketplace = tmp_path / "marketplace"

    result = run_installer(
        "--source",
        str(source),
        "--marketplace-root",
        str(marketplace),
        "--skip-register",
        "--verbose",
    )

    assert result.returncode == 0, result.stderr

    for name in ("shatter", "refute"):
        plugin_root = marketplace / "plugins" / name
        assert (plugin_root / ".codex-plugin" / "plugin.json").is_file()
        assert (plugin_root / "skills" / f"install-{name}" / "SKILL.md").is_file()

    manifest_path = marketplace / ".agents" / "plugins" / "marketplace.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "shatterproof"
    assert manifest["interface"]["displayName"] == "Shatterproof"

    entries = {plugin["name"]: plugin for plugin in manifest["plugins"]}
    assert set(entries) == {"shatter", "refute"}
    assert entries["shatter"]["source"] == {"source": "local", "path": "./plugins/shatter"}
    assert entries["refute"]["source"] == {"source": "local", "path": "./plugins/refute"}
    assert entries["shatter"]["policy"] == {
        "installation": "INSTALLED_BY_DEFAULT",
        "authentication": "ON_INSTALL",
    }
    assert entries["shatter"]["category"] == "Developer Tools"


def test_bootstrap_download_path_cleans_up_tmpdir(tmp_path: Path) -> None:
    # Exercise the download_source() path without real network access by
    # shadowing `curl` and `tar` on PATH. The fake `tar` populates the
    # extraction directory from a local fixture. After the bootstrap exits,
    # no temp directory it created under TMPDIR should remain on disk.
    fixture = tmp_path / "fixture"
    create_generated_plugin(fixture, "shatter")
    (fixture / "scripts").mkdir()
    installer_copy = fixture / "scripts" / "install-codex-plugins"
    shutil.copy2(SCRIPT, installer_copy)
    installer_copy.chmod(0o755)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    curl.chmod(0o755)
    tar = fake_bin / "tar"
    tar.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            # Drain stdin (the piped curl output) so curl does not see SIGPIPE.
            cat >/dev/null 2>&1 || true
            target=""
            while [[ $# -gt 0 ]]; do
              case "$1" in
                -C) target="$2"; shift 2;;
                *) shift;;
              esac
            done
            cp -a "$FIXTURE_SRC"/. "$target"/
            """
        ),
        encoding="utf-8",
    )
    tar.chmod(0o755)

    tmproot = tmp_path / "tmp"
    tmproot.mkdir()
    marketplace = tmp_path / "marketplace"

    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(tmproot),
        "FIXTURE_SRC": str(fixture),
        "CODEX_HOME": str(tmp_path / ".codex"),
    }
    env.pop("SHATTER_AGENTS_SOURCE", None)

    result = subprocess.run(
        [str(BOOTSTRAP), "--marketplace-root", str(marketplace), "--skip-register", "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    leftovers = sorted(p.name for p in tmproot.iterdir())
    assert leftovers == [], f"download_source leaked temp entries: {leftovers}"


def test_installer_can_install_one_named_plugin(tmp_path: Path) -> None:
    source = tmp_path / "source"
    create_generated_plugin(source, "shatter")
    create_generated_plugin(source, "refute")
    marketplace = tmp_path / "marketplace"

    result = run_installer(
        "refute",
        "--source",
        str(source),
        "--marketplace-root",
        str(marketplace),
        "--skip-register",
    )

    assert result.returncode == 0, result.stderr
    assert not (marketplace / "plugins" / "shatter").exists()
    assert (marketplace / "plugins" / "refute").is_dir()
