---
name: compose-shatter-recipe
description: Author and validate Shatter recipes that bind each parameter of a multi-resource async target to its own provider — a live/seeded resource, a registered stub, a pinned value, or default synthesis — so one run can combine, e.g., a real seeded database with an erroring storage stub. Covers the v1 recipe JSON schema, config-declared stub/scenario registration, the composed recipe generator, fail-fast validation, and recipe discovery.
---

## Model Guidance

Recommended model: high. Authoring a correct recipe requires reading the
target signature, matching parameter names and port types against a stub
registry, and reasoning about which branch a binding forces. Validation
diagnosis and the port-seam prerequisite call for qualitative judgment.

## Purpose

For downstream users of Shatter whose target is an async function that
takes several external resource handles as **independent parameters** and
who need to stub each resource independently — the case Shatter's default
single bundled `State()` synthesis cannot express.

The motivating shape is a function like:

```rust
async fn run_once(
    pool: &PgPool,
    config: &SweeperConfig,
    storage: &dyn Storage,
) -> Result<SweepReport, SweepError>
```

Reaching the `S3 delete fails, rows left for retry` branch needs two
independent things in one run: a **real** `PgPool` seeded with rows the
sweeper will try to delete, *and* a **stub** `Storage` whose
`delete_object` errors. "All live" or "all synthesized" cannot express
"live database, erroring storage". A recipe can.

This skill produces and validates the recipe document, the stub/scenario
registrations, and the supporting stub source. It does not author the
port-trait seam itself (that is a project-owned prerequisite — see
[Prerequisite: the port seam](#prerequisite-the-port-seam)).

## When to use

Use this skill when **all** of the following hold:

- The target is a function with two or more independent resource
  parameters.
- You need at least one parameter **stubbed** (forced to a specific
  behavior, e.g. an error) while at least one other stays **live** or
  seeded.
- The parameter you want to stub is already typed as a **port trait /
  interface** (e.g. `&dyn Storage`), not a concrete type.

Do **not** use this skill to make a target with no recipe behave
differently. A target with no recipe is unchanged — that is the
backward-compatible contract below. Single-resource or all-synthesized
targets need no recipe.

## Backward-compatibility contract (read first)

A recipe is an **optional overlay**. These invariants are load-bearing
and every change in this skill preserves them:

- A target with **no recipe** runs exactly as today: one bundled
  `State()` synthesis. No recipe is ever required.
- A recipe **only changes the parameters it names.** An **absent**
  binding for a parameter falls back to default synthesis — the
  status-quo path, never an error.
- The composed recipe generator is engaged **only when a recipe is
  attached** to the run. `State()` is otherwise untouched.

If a change to a recipe would alter the no-recipe path, it is wrong.

---

## 1. Recipe document format (v1 schema)

A recipe is a small declarative JSON document that binds each parameter
of one target function to a **provider**. Shatter resolves each binding
independently and assembles the argument tuple from the results.

### Document shape

```json
{
  "schemaVersion": 1,
  "target": "<path-relative-source>::<function>",
  "bindings": {
    "<paramName>": <binding-value>,
    "...": "..."
  }
}
```

- `schemaVersion` — explicit integer, currently `1`. The resolver
  **rejects an unknown version** rather than best-effort parsing it (see
  [Validation](#4-validation-fail-fast-before-the-run)).
- `target` — the function identity: source path **relative to the target
  root** plus the function name (and, where a language needs it, the
  enclosing type/module), e.g. `api/src/sweeper.rs::run_once`. This is the
  same identity Shatter already uses to address a spec.
- `bindings` — a map keyed by **parameter name** (see below).

### Bindings are keyed by parameter name

Keys are the target's **parameter names** — not type names, not
positional indices.

- Parameter name is unambiguous even when two parameters share a type
  (`from: &dyn Storage, to: &dyn Storage`). Type keys cannot tell those
  apart; positional indices are brittle under signature edits.
- The resolver validates every recipe key against the target's real
  parameter names at load time and errors on any key that does not match,
  catching typos and signature drift.

### Binding grammar

A binding value is either a **shorthand string** or an **object**. The
object form is the canonical expansion of the shorthand and is required
when a binding needs configuration. Reserved words (`live`, `stub`,
`default`, `value`, `with`) are the only special keys; **any other bare
string is rejected**, so a misspelled `"stub:..."` prefix cannot be
silently misread.

| Shorthand | Object form | Meaning |
|-----------|-------------|---------|
| `"live"` | `{ "live": true }` | Real resource via its default live setup. |
| — | `{ "live": "<scenario>" }` | Real resource via a named scenario factory. |
| `"stub:<name>"` | `{ "stub": "<name>" }` | Registered stub, default config. |
| — | `{ "stub": "<name>", "with": { … } }` | Registered stub with config passed verbatim to its factory. |
| `"default"` | `{ "default": true }` | Engine default synthesis (the status quo for that parameter). |
| — | `{ "value": <literal> }` | Pin a concrete literal value (plain-data params only). |
| *(key absent)* | — | Same as `"default"` — backward compatible. |

`"default"` (explicit) and an absent key are the **only** ways a
parameter gets default synthesis. Default is never reached as a fallback
from a failed stub or scenario lookup — that fails fast instead (see
[Validation](#4-validation-fail-fast-before-the-run)).

### Where recipes live

Recipes are project-owned artifacts under the target's Shatter config
directory:

```
.shatter/recipes/<target-id>/<recipe-name>.json
```

e.g. `.shatter/recipes/sweeper.run_once/s3-delete-fails.json`. The
`<target-id>` groups every recipe for one target; one target may have
several named recipes — typically one per branch family worth forcing.

---

## 2. Stub authoring and registration

### What a stub is

A stub is **ordinary project code** that implements the same port trait /
interface the target parameter depends on, written to drive one specific
branch (here: `delete_object` returns an error). Stubs are project-owned,
language-native, and compiled/loaded as part of the target — Shatter does
**not** synthesize trait implementations.

### Prerequisite: the port seam

A stub can be bound to a parameter **only if that parameter is a trait /
interface**, not a concrete type. `storage: &StorageClient` (concrete)
cannot be stubbed; `storage: &dyn Storage` (a narrow project-owned port)
can. The port seam is a **prerequisite owned by the project**, not part
of this feature — it is a `PROJECT-FIX` in the tractability taxonomy
(`docs/specs/2026-06-16-shatter-tractability-taxonomy.md`, *Small
Project-Owned Ports Or Interfaces Around Opaque Resources*). Recipes make
the seam *useful* by binding a stub to it; they do not create it. If the
parameter is still concrete, validation fails with a precise error (see
[Validation](#4-validation-fail-fast-before-the-run)) — do not try to
stub it; recommend the port refactor instead.

### Where stub files live

Stubs live in a conventional, config-declared location inside the
target's source tree so they compile with the project and can `use` its
real port trait and error types:

```
shatter/stubs/<lang>/<stub_source>
```

e.g. `shatter/stubs/rust/storage_delete_errors.rs`. The directory is a
normal part of the crate/module graph but **gated out of release
builds**:

- **Rust** — a `shatter_stubs` module behind a `shatter` cfg/feature so
  it never ships in release.
- **Go** — a `shatter` build tag on the stub files.
- **TypeScript** — a dev-only entrypoint, never imported from production
  code.

### Interface and factory a stub must provide

- A stub must implement **the exact port trait the target parameter is
  typed as** — the same trait the real resource satisfies. This is the
  contract that makes substitution type-safe.
- A stub exposes a **factory** that Shatter calls to obtain an instance:
  a zero-argument constructor for the default case, and (optionally) a
  config-accepting constructor used when the binding supplies `with`. The
  `with` object is passed to the factory **verbatim**; Shatter does not
  interpret it.
- Keep every method other than the branch driver **benign** (succeeding,
  plausible return values) so the stub does not mask the branch under
  test.

### Config-declared registry (v1)

**v1 decision: a config-declared registry.** `.shatter/config.yaml` gains
a `stubs:` section mapping each stub name to the metadata Shatter needs to
compile and construct it:

```yaml
stubs:
  - name: storage_delete_errors   # the name a recipe references
    implements: Storage           # the port trait it satisfies
    lang: rust
    source: shatter/stubs/rust/storage_delete_errors.rs
    factory: StorageDeleteErrors::new   # zero-arg constructor
```

A config-declared registry is chosen over compile-time attribute
discovery (e.g. a `#[shatter::stub]` macro collected via
`inventory`/`linkme`) for v1 because it is uniform across Go / Rust /
TypeScript, needs no engine-side macro support per language, and keeps the
name→type→constructor mapping in one auditable place the resolver can
validate before any code runs. Attribute-based auto-discovery is a
**future enhancement**, not a v1 requirement.

### Live scenarios (the live side of a recipe)

A `{ "live": "<scenario>" }` binding resolves to a **scenario factory**:
a deterministic seeding of a real resource (e.g. a `PgPool` pre-loaded
with sweep-eligible rows). Scenarios are registered alongside stubs in a
`scenarios:` section:

```yaml
scenarios:
  - name: rows_pending_delete
    parameter_type: PgPool
    lang: rust
    source: shatter/scenarios/rust/rows_pending_delete.rs
    factory: rows_pending_delete   # async fn(pool) seeds sweep-eligible rows
```

A bare `"live"` (no scenario name) uses the parameter's **default live
setup**. Either form requires a registered live setup/scenario; a named
scenario that is not registered fails validation.

---

## 3. Composed recipe generator

Multi-resource composition is a **new generator shape — the composed
recipe generator — not an extension of the `State()` contract.** The
existing `State()` generator remains the default and is unchanged: with no
recipe attached, a target gets one bundled synthesized state exactly as
today.

When a recipe **is** attached, the composed recipe generator takes the
place of the monolithic `State()` call for that target. Instead of
producing one bundled object, it resolves each parameter's binding
independently and assembles the results into the argument tuple:

```
composed_recipe_generator(target, recipe):
    for each parameter p of target:
        binding = recipe.bindings[p.name]  or  DEFAULT
        args[p] = resolve(binding):
            live "<scenario>"   -> run live setup / named scenario factory
            stub "<name>"       -> registry.lookup(name).factory(with?)
            value <literal>     -> use the literal
            default             -> existing State()/value synthesis for p
    return assemble(args)
```

Concolic exploration is unchanged in spirit: parameters resolved to
`default` (typically plain-data ones like `SweeperConfig`) are still
varied by the solver, while `live` and `stub` parameters are held fixed
for the run (a stub may itself expose generated knobs via `with`, but that
is opt-in). The recipe **narrows** the input surface to the slice that
reaches the target branch.

### Where it sits in the pipeline

Recipe resolution is at the **input-construction stage**, after target
discovery and **after validation**, before execution:

```
discover target
  -> [recipe attached?] -- no --> State() bundled synthesis  (unchanged path)
                        \- yes -> validate recipe (section 4)
                                  -> composed recipe generator (resolve bindings)
  -> assemble args
  -> invoke target
  -> observe branches / capture spec
```

Validation runs **first**, before any resource is constructed or any code
runs, so a bad recipe fails cheaply.

---

## 4. Validation: fail fast, before the run

**Decision: fail fast, before the run, with a precise error. No silent
default substitution.**

Silent substitution is actively misleading. If a recipe asks for
`storage_delete_errors` and Shatter quietly falls back to a storage that
*succeeds*, the run reports coverage of the happy path while the author
believes the `delete fails` branch was exercised. A coverage tool that
lies about which branch it reached is worse than one that refuses to run.

Validation runs **before execution** and errors on any of:

| Condition | Error |
|-----------|-------|
| Recipe key is not a real parameter of the target | `unknown parameter "<key>" for <target>; parameters are: ...` |
| `stub:<name>` not present in the registry | `no registered stub "<name>" (recipe <file>)` |
| Registered stub's `implements` ≠ the parameter's port type | `stub "<name>" implements <X>, but parameter <p> requires <Y>` |
| Parameter is a concrete type with no port seam | `parameter <p> is concrete type <T>; stubbing requires a port trait (see tractability taxonomy)` |
| `live` / `live:<scenario>` requested but no live setup / scenario factory registered | `no live setup for parameter <p>` (named: `no scenario "<s>" for <p>`) |
| Unknown `schemaVersion` | `unsupported recipe schemaVersion <n>` |

These conditions are **errors, not warnings** — in particular an unknown
`schemaVersion` and an unregistered stub name both stop the run. Do not
downgrade either to a warning.

**Not errors** — these use default synthesis deliberately:

- An **absent** binding for a parameter → default synthesis (the
  backward-compatible path).
- An explicit `"default"` → default synthesis, opted into on purpose.

So: *explicit-but-unresolvable* bindings error; *unspecified* bindings
default. The only way to get a default for a parameter is to omit it or
write `"default"` — never as a fallback from a failed lookup.

---

## 5. Recipe discovery

`run-shatter` enumerates recipes per target so a run can explore each one.
For every discovered target with id `<target-id>`, recipe discovery globs:

```
.shatter/recipes/<target-id>/*.json
```

Each matched file is one named recipe for that target. A target with no
matching directory or no `*.json` files simply has no recipes and runs the
unchanged bundled path — discovery never fails on an absent recipe
directory. Validation (section 4) runs per recipe before that recipe's run
is attempted; a malformed recipe fails its own run with the precise error
above without aborting the other targets or recipes. See the
`run-shatter` skill (*Recipe discovery and runs* section) for how the run
surface enumerates and reports per-recipe results.

---

## 6. Worked reference — pickpackit sweeper

This is the end-to-end reference: the port seam (prerequisite), the
recipe, the config registration, and the stub source. A full copy of the
recipe and the supporting files also ships as companions under
`references/` so they can be applied verbatim.

### Target (with the port seam applied)

```rust
async fn run_once(
    pool: &PgPool,
    config: &SweeperConfig,
    storage: &dyn Storage,
) -> Result<SweepReport, SweepError>
```

`storage` is typed as `&dyn Storage` — the narrow project-owned port. The
seam is the prerequisite; the recipe binds a stub to it.

### Recipe — force `S3 delete fails, rows left for retry`

`.shatter/recipes/sweeper.run_once/s3-delete-fails.json`:

```json
{
  "schemaVersion": 1,
  "target": "api/src/sweeper.rs::run_once",
  "bindings": {
    "pool":    { "live": "rows_pending_delete" },
    "config":  "default",
    "storage": { "stub": "storage_delete_errors" }
  }
}
```

Reading the recipe:

- `pool` → a **real** `PgPool` seeded by the named scenario factory
  `rows_pending_delete`, which inserts rows the sweeper will try to
  delete.
- `config` → **default** synthesis; the solver varies `SweeperConfig`
  (batch size, retry thresholds) freely.
- `storage` → the **registered stub** `storage_delete_errors`, whose
  `delete_object` always errors, forcing the retry branch.

This run pairs a real, seeded database with an erroring storage stub — the
exact combination the bundled-state model cannot express. It resolves to a
real seeded `PgPool` + erroring `Storage` stub and reaches the
`rows left for retry` branch.

### Supporting `.shatter/config.yaml`

```yaml
stubs:
  - name: storage_delete_errors
    implements: Storage
    lang: rust
    source: shatter/stubs/rust/storage_delete_errors.rs
    factory: StorageDeleteErrors::new

scenarios:
  - name: rows_pending_delete
    parameter_type: PgPool
    lang: rust
    source: shatter/scenarios/rust/rows_pending_delete.rs
    factory: rows_pending_delete   # async fn(pool) seeds sweep-eligible rows
```

### Stub source — `shatter/stubs/rust/storage_delete_errors.rs`

```rust
use crate::storage::{Storage, StorageError};   // the project's port + error type
use async_trait::async_trait;

/// Registered in .shatter/config.yaml as "storage_delete_errors".
pub struct StorageDeleteErrors;

impl StorageDeleteErrors {
    pub fn new() -> Self {
        StorageDeleteErrors
    }
}

#[async_trait]
impl Storage for StorageDeleteErrors {
    /// The branch driver: deletes always fail, so the sweeper must leave rows
    /// for retry instead of marking them done.
    async fn delete_object(&self, _key: &str) -> Result<(), StorageError> {
        Err(StorageError::Io("simulated S3 delete failure".into()))
    }

    /// Other methods stay benign so they don't mask the branch under test.
    async fn put_object(&self, _key: &str, _bytes: &[u8]) -> Result<(), StorageError> {
        Ok(())
    }

    async fn object_exists(&self, _key: &str) -> Result<bool, StorageError> {
        Ok(true)
    }
}
```

The `Storage` port (the prerequisite seam, owned by the project) is the
narrow trait `run_once` accepts as `storage: &dyn Storage`.

---

## Authoring workflow

1. **Confirm the seam.** Verify the parameter you want to stub is a port
   trait, not a concrete type. If concrete, stop and recommend the port
   refactor (taxonomy `PROJECT-FIX`) — do not attempt to stub it.
2. **Author the stub** under `shatter/stubs/<lang>/`, implementing the
   exact port trait with a benign body except the branch driver. Gate it
   out of release builds.
3. **Author any live scenario** under `shatter/scenarios/<lang>/` that
   seeds the real resource deterministically.
4. **Register** the stub (and scenario) in `.shatter/config.yaml` under
   `stubs:` / `scenarios:`, mapping name → `implements`/`lang`/`source`/
   `factory` (scenario: name → `parameter_type`/`lang`/`source`/`factory`).
5. **Write the recipe** at `.shatter/recipes/<target-id>/<name>.json`
   with `schemaVersion: 1`, the `target` id, and a `bindings` map keyed by
   parameter name. Bind only the parameters you need to control; omit the
   rest to keep default synthesis.
6. **Validate mentally against section 4** before running: every key is a
   real parameter; every named stub/scenario is registered; each stub's
   `implements` equals the parameter's port type; `schemaVersion` is 1.

---

## Out of scope

- Authoring the port-trait refactor for any specific target
  (project-owned prerequisite; taxonomy `PROJECT-FIX`).
- Attribute/annotation-based stub auto-discovery (future enhancement).
- Generated knobs inside stubs beyond the `with` config object passed
  verbatim to the factory.
- Cross-target shared stub libraries / packaging.
- Running the targets or reviewing run output — that is `run-shatter`.

## Required companion

- `references/s3-delete-fails.json` — the worked pickpackit recipe,
  applyable verbatim.
- `references/config.snippet.yaml` — the `stubs:` + `scenarios:`
  registration for the worked example.
- `references/storage_delete_errors.rs` — the worked stub source.

This skill also relies on the design of record in
`docs/specs/2026-06-24-recipe-schema-design.md` and composes with the
tractability taxonomy in
`docs/specs/2026-06-16-shatter-tractability-taxonomy.md`. Recipe
**discovery and per-recipe runs** are surfaced by the `run-shatter` skill.
