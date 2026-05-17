from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_lists_exactly_catalog_plugins():
    plugins = json.loads((REPO_ROOT / "catalog" / "plugins.json").read_text())["plugins"]
    mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    listed = [p["name"] for p in mp["plugins"]]
    assert sorted(listed) == sorted(plugins.keys())


def test_marketplace_sources_resolve_to_existing_dirs():
    mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in mp["plugins"]:
        src = REPO_ROOT / entry["source"].lstrip("./")
        assert src.is_dir(), f"{src} missing for {entry['name']}"
        assert (src / ".claude-plugin" / "plugin.json").is_file()


def test_marketplace_versions_match_plugin_manifests():
    mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in mp["plugins"]:
        manifest = json.loads(
            (REPO_ROOT / entry["source"].lstrip("./") / ".claude-plugin" / "plugin.json").read_text()
        )
        assert manifest["version"] == entry["version"]
