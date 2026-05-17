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
