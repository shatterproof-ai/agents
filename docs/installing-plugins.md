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

Codex plugins from this marketplace can be installed from the generated
`plugins/codex/<name>/` directories. The Codex side of this marketplace
does not currently register custom slash commands; invoke skills by name
in your prompt instead, for example:

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
