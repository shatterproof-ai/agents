# Skill Overlays

A canonical skill lives under `catalog/skills/<name>/SKILL.md`. When the
behavior is identical across Claude Code and Codex, that file is the
entire skill.

When a skill needs target-specific text, add an overlay file in the same
directory:

- `CLAUDE.md` — appended to the composed Claude Code skill body
- `CODEX.md` — appended to the composed Codex skill body

Overlays must:

- Start with a level-2 heading (`## ...`).
- Contain no YAML frontmatter (only the canonical `SKILL.md` defines the
  frontmatter).

The builder appends each overlay verbatim after the canonical body,
separated by a horizontal rule.

## Why `metadata.json` instead of frontmatter keys

Per-skill metadata such as `recommended_model` lives in `metadata.json`
next to `SKILL.md`, not in the frontmatter. Reasons:

1. **Semantic non-portability.** The three-bucket `low|mid|high` mapping
   is Claude-shaped (Haiku / Sonnet / Opus). Codex, Gemini, and local
   model runtimes do not share a single three-tier hierarchy.
2. **Schema non-portability.** SKILL.md frontmatter is the typed contract
   the host runtime parses. Unknown keys happen to work today but are not
   part of any documented spec.
3. **Temporal non-portability.** Bucket labels have no version pin. The
   prose `## Model Guidance` section in the body ages better than the
   label.

`metadata.json` is plain JSON, copied verbatim into generated plugins.
Any future discovery tool can read it without touching the SKILL contract.
