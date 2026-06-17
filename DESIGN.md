# Shatterproof Marketplace — Design

`shatter-agents` is a plugin marketplace for Claude Code and Codex that ships
two plugins (`shatter`, `refute`) built from canonical sources under
`catalog/`. This is a short pointer file. The canonical design document is at
[`docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md`](docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md).

Specs:

- [`docs/specs/2026-06-16-shatter-tractability-taxonomy.md`](docs/specs/2026-06-16-shatter-tractability-taxonomy.md)
  — how Shatter findings are classified by tractability and disposition.

Conventions split out into their own documents:

- [`docs/conventions/overlays.md`](docs/conventions/overlays.md) — how
  `CLAUDE.md` and `CODEX.md` overlays compose with shared `SKILL.md`.
- [`docs/conventions/companion-files.md`](docs/conventions/companion-files.md)
  — semantics of `references/` and `scripts/` under each skill.
- [`docs/conventions/versioning.md`](docs/conventions/versioning.md) —
  auto-versioning, content-hash inputs, and how to do a manual major/minor
  bump.
