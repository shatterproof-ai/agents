#!/usr/bin/env python3
"""Insert or replace a tool's usage stanza in a project's primary agent doc."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def pick_target(project_root: Path, tool: str) -> tuple[Path, bool]:
    for candidate in ("AGENTS.md", "CLAUDE.md"):
        p = project_root / candidate
        if p.is_file():
            return p, False
    return project_root / "docs" / f"{tool}-usage.md", True


def build_stanza(tool: str, version: str | None, backends: list[str], skills: list[str]) -> str:
    label = tool.capitalize()
    lines = [f"## {label} Usage", ""]
    if version:
        lines.append(f"- Installed version: `{version}`")
    if backends:
        lines.append(f"- Backends installed: {', '.join(f'`{b}`' for b in backends)}")
    if skills:
        lines.append(f"- Suggested skills: {', '.join(f'`{s}`' for s in skills)}")
    lines.append("")
    lines.append(f"See upstream documentation for command reference.")
    return "\n".join(lines) + "\n"


def upsert_stanza(text: str, tool: str, stanza_body: str) -> str:
    open_marker = f"<!-- {tool}:usage -->"
    close_marker = f"<!-- /{tool}:usage -->"
    block = f"{open_marker}\n{stanza_body.rstrip()}\n{close_marker}"
    pattern = re.compile(
        rf"{re.escape(open_marker)}.*?{re.escape(close_marker)}",
        flags=re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(block, text)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "\n" + block + "\n"


def ensure_readme_pointer(project_root: Path, doc_path: Path, tool: str) -> None:
    readme = project_root / "README.md"
    rel = doc_path.relative_to(project_root).as_posix()
    open_marker = f"<!-- {tool}:pointer -->"
    close_marker = f"<!-- /{tool}:pointer -->"
    block = (
        f"{open_marker}\n"
        f"See [{tool} usage](./{rel}) for setup notes.\n"
        f"{close_marker}\n"
    )
    if readme.exists():
        existing = readme.read_text(encoding="utf-8")
        pattern = re.compile(
            rf"{re.escape(open_marker)}.*?{re.escape(close_marker)}\n?",
            flags=re.DOTALL,
        )
        if pattern.search(existing):
            new = pattern.sub(block, existing)
        else:
            if existing and not existing.endswith("\n"):
                existing += "\n"
            new = existing + "\n" + block
        readme.write_text(new, encoding="utf-8")
    else:
        readme.write_text(f"# Project\n\n{block}", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True, choices=["shatter", "refute"])
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--version", default=None)
    parser.add_argument("--backend", action="append", default=[])
    parser.add_argument("--skill", action="append", default=[])
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    target, is_new = pick_target(root, args.tool)
    stanza = build_stanza(args.tool, args.version, args.backend, args.skill)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        target.read_text(encoding="utf-8")
        if target.exists()
        else f"# {args.tool.capitalize()} Usage\n\n"
    )
    target.write_text(upsert_stanza(existing, args.tool, stanza), encoding="utf-8")
    if is_new:
        ensure_readme_pointer(root, target, args.tool)
    print(f"Updated {target.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
