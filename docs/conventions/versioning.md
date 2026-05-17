# Plugin Versioning

Each plugin's current version is stored in
`catalog/plugin-versions.json`:

```json
{
  "shatter": { "version": "0.1.1", "content_hash": "sha256:..." },
  "refute":  { "version": "0.1.0", "content_hash": "sha256:..." }
}
```

## Auto-bumped patches

When `scripts/build-plugins` runs, it computes a content hash over each
plugin's freshly generated tree. The hash inputs:

- sorted file paths within `plugins/claude/<plugin>/`
- per-file SHA-256
- excludes the `version` field of the manifest itself (so a version bump
  alone does not feed back into the hash)

If the new hash differs from the recorded hash:

- If the recorded `version` has `patch > 0`, the builder bumps the patch by
  one and writes the new hash.
- If the recorded `version` has `patch == 0`, the builder leaves the
  version alone and only updates the hash. `patch == 0` is the
  **manual-bump anchor**: it indicates the version was just set by a
  human (initial `0.1.0`, or a manual bump to `1.0.0` / `2.3.0`), and the
  builder should not auto-bump it on the first content-change after.

If the hash matches, no-op.

## Manual major or minor bumps

Edit `catalog/plugin-versions.json` directly and set `version` to your
target — always with `patch = 0`. Example: bumping `1.2.7` to `2.0.0`.
The next build sees the patch=0 anchor and records the new hash without
auto-bumping; subsequent content changes resume the auto-bump at
`2.0.1`, `2.0.2`, and so on.

## Why this approach

- No separate bump script (bento's `bump-plugin-versions` is replaced by
  the builder).
- Idempotent: running the builder twice in a row never changes either
  the versions file or the generated tree.
- CI catches missed rebuilds via `scripts/check-plugins-clean`, which
  diffs the committed `plugins/` and versions file against a fresh build.
