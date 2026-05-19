# Installing Shatterproof Plugins

## Claude Code

Add the marketplace to your settings (`~/.claude/settings.json` for
home-scope, or `.claude/settings.local.json` for project-scope):

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": {
      "source": { "source": "github", "repo": "shatterproof-ai/shatter-agents" }
    }
  }
}
```

Then `/plugins install shatterproof:shatter` or
`/plugins install shatterproof:refute`.

## OpenAI Codex

Codex plugins from this marketplace are generated under:

- `plugins/codex/shatter/`
- `plugins/codex/refute/`

Each generated plugin has a `.codex-plugin/plugin.json` manifest and a
`skills/` directory. Install both plugins into a local Codex marketplace:

```bash
curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter-agents/main/install/codex-home.sh | bash
```

From a cloned checkout, run the local installer directly:

```bash
scripts/install-codex-plugins
```

By default this:

1. Copies `plugins/codex/shatter/` and `plugins/codex/refute/` into
   `${CODEX_HOME:-~/.codex}/marketplaces/shatterproof/plugins/`.
2. Writes the Codex marketplace manifest at
   `${CODEX_HOME:-~/.codex}/marketplaces/shatterproof/.agents/plugins/marketplace.json`.
3. Registers that marketplace with:

   ```bash
   codex plugin marketplace add ${CODEX_HOME:-~/.codex}/marketplaces/shatterproof
   ```

Restart any running Codex session after installation. To install just one
plugin, pass its name:

```bash
scripts/install-codex-plugins shatter
scripts/install-codex-plugins refute
```

Useful options:

- `--codex-home <path>`: register against a non-default Codex home.
- `--marketplace-root <path>`: write the marketplace somewhere else.
- `--skip-register`: write the marketplace but do not call the Codex CLI.
- `--dry-run`: show the planned install without writing files.
- `-v, --verbose`: print each major step.

Verify the install by opening Codex, running `/plugins`, and confirming the
`Shatter` and `Refute` plugins appear. The Codex side of this marketplace
does not currently register custom slash commands; invoke skills by name in
your prompt, for example:

> Use the `install-shatter` skill to set up Shatter in this project.

## Offline install

Clone the repo and point your Claude Code config at the local path:

```json
{
  "extraKnownMarketplaces": {
    "shatterproof": { "source": { "source": "path", "path": "/abs/path/to/shatter-agents" } }
  }
}
```
