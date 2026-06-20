# Installing Shatterproof Plugins

This marketplace ships two plugins: **shatter** (run Shatter, review results,
draft issue reports) and **refute** (symbol-aware refactoring via LSP).

## Claude Code

Add the `shatterproof` marketplace to your settings. For a home-scoped install
edit `~/.claude/settings.json`; for project-scope use
`.claude/settings.local.json`:

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": {
      "source": { "source": "github", "repo": "shatterproof-ai/shatter-agents" }
    }
  }
}
```

Then install either or both plugins:

```
/plugins install shatterproof:shatter
/plugins install shatterproof:refute
```

Or select them from the Claude Code plugin chooser.

**Offline / local checkout:** point the marketplace at a cloned path instead:

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": {
      "source": { "source": "path", "path": "/abs/path/to/shatter-agents" }
    }
  }
}
```

## OpenAI Codex

### 1 — Register the marketplace

```bash
curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter-agents/main/install/codex-home.sh | bash
```

This downloads the repository, copies the generated plugin artifacts into
`~/.codex/marketplaces/shatterproof/`, and runs
`codex plugin marketplace add` to register it.

From a cloned checkout you can skip the download:

```bash
scripts/install-codex-plugins
```

### 2 — Add the plugins

After the marketplace is registered, enable the plugins you want:

```bash
codex plugin add shatter@shatterproof
codex plugin add refute@shatterproof
```

### 3 — Verify

```bash
codex plugin list
```

Both plugins should show `installed, enabled` at version `0.1.1`.

Restart any running Codex session to load the new plugins. Invoke skills by
name in your prompt — for example:

> Use the `install-shatter` skill to set up Shatter in this project.

### Install options

Pass extra flags through the curl installer with `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter-agents/main/install/codex-home.sh | bash -s -- --skip-register
```

Or when running the local installer directly:

| Flag | Effect |
|---|---|
| `shatter` / `refute` | Install only the named plugin |
| `--codex-home <path>` | Use a non-default Codex home |
| `--marketplace-root <path>` | Write the marketplace to a custom path |
| `--skip-register` | Copy files but do not call `codex plugin marketplace add` |
| `--dry-run` | Show what would be installed without writing files |
| `-v, --verbose` | Print each major step |

See [`docs/installing-plugins.md`](docs/installing-plugins.md) for full
details.
