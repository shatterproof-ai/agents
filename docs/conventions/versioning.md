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

- The builder bumps the patch by one and writes the new hash.
- `patch == 0` is the **manual-bump anchor**: it indicates the version was
  just set by a human (initial `0.1.0`, or a manual bump to `1.0.0` /
  `2.3.0`). On the first content change after a manual bump, the builder
  bumps patch to 1 (consuming the anchor), so `2.0.0` becomes `2.0.1`.
  Subsequent content changes resume normal auto-bumping: `2.0.2`, `2.0.3`,
  and so on.

If the hash matches, no-op.

## Manual major or minor bumps

Edit `catalog/plugin-versions.json` directly and set `version` to your
target — always with `patch = 0`. Example: bumping `1.2.7` to `2.0.0`.
The next content change bumps patch to 1 (`2.0.1`), then auto-bumping
resumes normally: `2.0.2`, `2.0.3`, and so on.

## Why this approach

- No separate bump script (bento's `bump-plugin-versions` is replaced by
  the builder).
- Idempotent: running the builder twice in a row never changes either
  the versions file or the generated tree.
- CI catches missed rebuilds via `scripts/check-plugins-clean`, which
  diffs the committed `plugins/` and versions file against a fresh build.
