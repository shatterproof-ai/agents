# Skill Companion Files

A skill directory may include companion files alongside `SKILL.md` and
`metadata.json`:

```
catalog/skills/<name>/
├── SKILL.md
├── metadata.json
├── references/         # data the skill body cites
└── scripts/            # deterministic helpers the skill body invokes
```

## When to write a companion script vs prose

Push logic into a companion script when it is:

- repeatable and benefits from machine-checkable output (JSON)
- stateful or high-cost if misclassified
- dependent on repo facts, git state, or precise file parsing

Keep logic in `SKILL.md` prose when it is:

- qualitative or judgment-heavy
- dependent on user preferences or trade-offs
- policy, framing, or workflow guidance

## Layout in generated plugins

`references/` and `scripts/` are copied verbatim into
`plugins/<target>/<plugin>/skills/<skill>/`. Executable bits on scripts
are preserved.

## Cross-skill references

Two skills in the **same plugin** can reference each other's companion
files via relative paths. Example: `report-shatter-issues/SKILL.md`
references `../../run-shatter/references/report-schema.md` because both
skills ship in the `shatter` plugin.

Cross-plugin references are not supported. If two plugins genuinely need
the same helper, duplicate it (the v1 example is
`update_usage_stanza.py`, byte-identical in `install-shatter` and
`install-refute`).
