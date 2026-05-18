# shatter-agents — Shatterproof Marketplace

A plugin marketplace for [Shatter](https://github.com/shatterproof-ai/shatter)
and [Refute](https://github.com/shatterproof-ai/refute), targeting Claude
Code and OpenAI Codex.

## Plugins

| Plugin | Description |
|---|---|
| `shatter` | Install, run, and review Shatter; draft markdown issue reports. |
| `refute`  | Install Refute and diagnose its setup for symbol-aware refactoring. |

## Install (Claude Code)

Add the marketplace to your settings:

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": {
      "source": { "source": "github", "repo": "shatterproof-ai/shatter-agents" }
    }
  }
}
```

Then install either or both plugins from the Claude Code plugin chooser.

See [`docs/installing-plugins.md`](docs/installing-plugins.md) for Codex
install instructions and offline notes.

## Install (OpenAI Codex)

Generated Codex plugin artifacts are committed under `plugins/codex/shatter/`
and `plugins/codex/refute/`. From the repository root, install both into a
local Codex marketplace:

```bash
scripts/install-codex-plugins
```

Then restart Codex and verify the `Shatter` and `Refute` plugins appear in
`/plugins`. See [`docs/installing-plugins.md`](docs/installing-plugins.md)
for single-plugin installs and non-default Codex home paths.

## Repository structure

- `catalog/` — canonical sources for skills and plugin metadata.
- `plugins/` — generated, committed plugin trees consumed by Claude Code
  and Codex. Do not edit by hand; edit `catalog/` and rebuild.
- `scripts/build-plugins` — regenerates `plugins/` and
  `.claude-plugin/marketplace.json`. Patch versions auto-bump on content
  change.
- `scripts/check-plugins-clean` — CI gate that fails if generated output
  has drifted from the canonical sources.

See [`DESIGN.md`](DESIGN.md) and
[`docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md`](docs/superpowers/specs/2026-05-16-shatterproof-marketplace-design.md)
for the full design.

## Tracker

Issues live in the in-repo Beads tracker (`.beads/`). Run `bd list` to
see what is open.
