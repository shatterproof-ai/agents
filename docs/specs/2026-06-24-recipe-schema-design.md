# Recipe Schema and Stub Registration for Independent Resource Stubbing

Status: design spike (sa-mty). No implementation. This document resolves the
four design questions required before implementation can begin and is concrete
enough that a full recipe for the pickpackit sweeper case is written out below.

## Problem

A function that takes several external resource handles as independent
parameters cannot today have each resource stubbed independently. Shatter's
generator model produces one bundled state object: it constructs the whole
argument surface together and has no way to combine a *real* instance of one
resource with a *stub* of another.

The motivating target is pickpackit's sweeper:

```rust
// api/src/sweeper.rs
async fn run_once(
    pool: &PgPool,
    config: &SweeperConfig,
    storage: &StorageClient,
) -> Result<SweepReport, SweepError>
```

Reaching the `S3 delete fails, rows left for retry` branch requires two
independent things at once:

- a **real** `PgPool` (or a faithful scenario over one) that returns rows the
  sweeper believes it should delete, and
- a **stub** storage handle whose `delete_object` returns an error, so the
  sweeper takes the retry path instead of marking the rows done.

The current model can express "all live" or "all synthesized", but not "live
database, erroring storage". This is the gap.

## Relationship to the tractability taxonomy

This design composes with, and does not replace, the existing guidance in
`docs/specs/2026-06-16-shatter-tractability-taxonomy.md`. Two patterns from that
document are load-bearing here:

- **Small Project-Owned Ports Or Interfaces Around Opaque Resources.** A stub
  can only be substituted for a parameter if that parameter is a *trait /
  interface*, not a concrete type. `storage: &StorageClient` (a concrete type)
  cannot be stubbed; `storage: &dyn Storage` (a narrow project-owned port) can.
  The port seam is therefore a **prerequisite** for stubbing a given parameter,
  not part of this feature. Recipes make the seam *useful* by letting Shatter
  bind a stub to it.
- **Scenario / State Factories For IO That Must Remain.** The "live" side of a
  recipe is exactly a scenario factory: a deterministic seeding of a real
  resource (e.g. a `PgPool` pre-loaded with rows that are due for sweeping).
  Recipes let a single run pair one named scenario for one parameter with a
  stub for another.

Multi-resource stubbing is the missing **composition layer** that lets these
two existing ideas be combined per parameter in one run.

---

## Q1 — Recipe schema

### What a recipe is

A recipe is a small declarative document that binds each parameter of one
target function to a **provider**: a live resource, a registered stub, a pinned
value, or the engine's default synthesis. Shatter resolves each binding
independently and assembles the argument tuple from the results.

Recipes are an optional overlay. A target with no recipe behaves exactly as
today (single bundled `State()` synthesis). A recipe only changes the
parameters it names; unnamed parameters keep default behavior. This keeps the
change backward compatible.

### Key naming convention: parameter name

Bindings are keyed by **parameter name**, not type name and not a positional
index.

- Parameter name is unambiguous within a single signature, even when two
  parameters share a type (`from: &dyn Storage, to: &dyn Storage`). Type-name
  keys cannot distinguish those; positional indices are brittle under signature
  edits and unreadable.
- Parameter names are stable, human-readable, and already how an author thinks
  about the call.
- The resolver validates recipe keys against the target's real parameter names
  at load time and errors on any key that does not match (catches typos and
  signature drift — see Q4).

### Value format (binding grammar)

A binding value is either a **shorthand string** or an **object**. The two
forms are interchangeable; the object form is the canonical expansion of the
shorthand and is required when a binding needs configuration.

| Shorthand | Object form | Meaning |
|-----------|-------------|---------|
| `"live"` | `{ "live": true }` | Real resource via its default live setup. |
| — | `{ "live": "<scenario>" }` | Real resource via a named scenario factory. |
| `"stub:<name>"` | `{ "stub": "<name>" }` | Registered stub, default config. |
| — | `{ "stub": "<name>", "with": { … } }` | Registered stub with config. |
| `"default"` | `{ "default": true }` | Engine default synthesis (the status quo for that parameter). |
| — | `{ "value": <literal> }` | Pin a concrete literal value (plain-data params only). |
| *(absent)* | — | Same as `"default"` — backward compatible. |

Reserved words (`live`, `stub`, `default`, `value`, `with`) are the only
special keys; any other bare string is rejected rather than guessed at, so a
misspelled `"stub:..."` prefix cannot be silently misread as something else.

### Schema version

The document carries an explicit integer `schemaVersion`, starting at `1`. The
resolver rejects an unknown major version rather than best-effort parsing it.
This mirrors the project's existing versioning posture
(`docs/conventions/versioning.md`).

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

- `target` identifies the function: source path relative to the target root
  plus the function name (and, where a language needs it, the enclosing
  type/module), e.g. `api/src/sweeper.rs::run_once`. This is the same
  identity Shatter already uses to address a spec.
- `bindings` is the per-parameter map described above.

### Where recipes live

Recipes are project-owned artifacts under the target's Shatter config
directory:

```
.shatter/recipes/<target-id>/<recipe-name>.json
```

e.g. `.shatter/recipes/sweeper.run_once/s3-delete-fails.json`. One target may
have several named recipes (one per branch family worth forcing). The
`run-shatter` discovery surface enumerates them alongside the target so a run
can explore each.

---

## Q2 — Stub authoring and registration

### What a stub is

A stub is **ordinary project code** that implements the same port trait /
interface the target parameter depends on, written to drive a specific branch
(here: `delete_object` returns an error). Stubs are project-owned, language
native, and compiled/loaded as part of the target — Shatter does not synthesize
trait implementations.

### Where stub files live

Stubs live in a conventional, config-declared location in the target's source
tree so they compile with the project and can `use` the project's real port
trait and error types:

```
shatter/stubs/<lang>/<stub_source>
```

e.g. `shatter/stubs/rust/storage_delete_errors.rs`. The directory is a normal
part of the crate/module graph (for Rust, a `shatter_stubs` module gated behind
a `shatter` cfg/feature so it never ships in release builds; analogous gating
in Go via a build tag, in TypeScript via a dev-only entrypoint).

### Interface a stub must implement

A stub must implement **the exact port trait the target parameter is typed as**.
This is the contract that makes substitution type-safe; it is the same trait the
real resource satisfies. If the parameter is still a concrete type, there is no
seam and the recipe cannot bind a stub to it (the taxonomy port refactor is the
prerequisite, and Q4 makes the failure explicit).

A stub also exposes a **factory** that Shatter calls to obtain an instance: a
zero-argument constructor for the default case, and an optional
config-accepting constructor when the binding supplies `with`.

### How Shatter discovers registered stubs by name

**v1 decision: a config-declared registry.** `.shatter/config.yaml` gains a
`stubs:` section mapping each stub name to the metadata Shatter needs to compile
it in and construct it:

```yaml
stubs:
  - name: storage_delete_errors   # the name a recipe references
    implements: Storage           # the port trait it satisfies
    lang: rust
    source: shatter/stubs/rust/storage_delete_errors.rs
    factory: StorageDeleteErrors::new   # zero-arg constructor
```

A config-declared registry is chosen over compile-time attribute discovery
(e.g. a `#[shatter::stub]` macro collected via an `inventory`/`linkme`-style
registry) for v1 because it is uniform across Go / Rust / TypeScript, needs no
engine-side macro support per language, and keeps the name→type→constructor
mapping in one auditable place that the resolver can validate before any code
runs. Attribute-based auto-discovery is recorded as a **future enhancement**,
not a v1 requirement.

### Stub authoring example (Rust pseudocode)

A stub `StorageClient` (port: `Storage`) that errors on `delete_object` and is
otherwise benign:

```rust
// shatter/stubs/rust/storage_delete_errors.rs
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

The corresponding `Storage` port (the prerequisite seam, owned by the project,
not by this feature) is the narrow trait `run_once` would accept as
`storage: &dyn Storage`.

---

## Q3 — Generator interface placement

### A new generator shape, layered over `State()`

Multi-resource composition is introduced as a **new generator shape — the
composed recipe generator — not an extension of the `State()` contract.** The
existing `State()` generator remains the default and is unchanged: with no
recipe attached, a target still gets one bundled synthesized state exactly as
today.

When a recipe *is* attached, the composed recipe generator takes the place of
the monolithic `State()` call for that target. Instead of producing one bundled
object, it produces the argument tuple by resolving each parameter's binding
independently and assembling the results:

```
composed_recipe_generator(target, recipe):
    for each parameter p of target:
        binding = recipe.bindings[p.name]  or  DEFAULT
        args[p] = resolve(binding):
            live "<scenario>"   -> run live setup / named scenario factory
            stub "<name>"       -> registry.lookup(name).factory(with?)
            value <literal>     -> use literal
            default             -> existing State()/value synthesis for p
    return assemble(args)
```

Concolic exploration is unchanged in spirit: parameters resolved to `default`
(typically plain-data ones like `SweeperConfig`) are still varied by the
solver, while `live` and `stub` parameters are held fixed for the run (a stub
may itself expose generated knobs via `with`, but that is opt-in). The recipe
*narrows* the input surface to the slice that reaches the target branch.

### Where it applies in the pipeline

Recipe resolution sits at the **input-construction stage**, after target
discovery and before execution:

```
discover target
  -> [recipe attached?] -- no --> State() bundled synthesis  (unchanged path)
                        \- yes -> validate recipe (Q4)
                                  -> composed recipe generator (resolve bindings)
  -> assemble args
  -> invoke target
  -> observe branches / capture spec
```

Validation (Q4) runs first, before any resource is constructed or any code is
executed, so a bad recipe fails cheaply.

---

## Q4 — Fallback behavior

**Decision: fail fast, before the run, with a precise error. No silent default
substitution.**

When a recipe names a stub for which no registered stub exists for that type,
Shatter must error at recipe-validation time — before constructing resources or
executing the target — rather than substituting a default.

Rationale: silent substitution is actively misleading. If a recipe asks for
`storage_delete_errors` and Shatter quietly falls back to a synthesized or live
storage that *succeeds*, the run would report coverage of the happy path while
the author believes the `delete fails` branch was exercised. A coverage tool
that lies about which branch it reached is worse than one that refuses to run.

Validation, performed before execution, errors on any of:

| Condition | Error |
|-----------|-------|
| Recipe key is not a real parameter of the target | `unknown parameter "<key>" for <target>; parameters are: ...` |
| `stub:<name>` not present in the registry | `no registered stub "<name>" (recipe <file>)` |
| Registered stub's `implements` ≠ the parameter's port type | `stub "<name>" implements <X>, but parameter <p> requires <Y>` |
| Parameter is a concrete type with no port seam | `parameter <p> is concrete type <T>; stubbing requires a port trait (see tractability taxonomy)` |
| `live`/`live:<scenario>` requested but no live setup/scenario factory registered | `no live setup for parameter <p>` (named scenario: `no scenario "<s>" for <p>`) |
| Unknown `schemaVersion` | `unsupported recipe schemaVersion <n>` |

Distinctions that are **not** errors:

- An **absent** binding for a parameter falls back to default synthesis — this
  is the backward-compatible path, not an error.
- An explicit `"default"` opts a parameter into default synthesis deliberately.

So: *explicit-but-unresolvable* bindings error; *unspecified* bindings default.
The only way to get a default for a parameter is to omit it or write `"default"`
explicitly — never as a fallback from a failed stub lookup.

---

## Full sample recipe — pickpackit sweeper

Target (with the port seam applied — `storage` typed as `&dyn Storage`):

```rust
async fn run_once(
    pool: &PgPool,
    config: &SweeperConfig,
    storage: &dyn Storage,
) -> Result<SweepReport, SweepError>
```

Recipe forcing the `S3 delete fails, rows left for retry` branch
(`.shatter/recipes/sweeper.run_once/s3-delete-fails.json`):

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
  `rows_pending_delete`, which inserts rows the sweeper will try to delete.
- `config` → **default** synthesis; the solver varies `SweeperConfig` (batch
  size, retry thresholds) freely.
- `storage` → the **registered stub** `storage_delete_errors`, whose
  `delete_object` always errors, forcing the retry branch.

Supporting `.shatter/config.yaml` entry (stub registry + the live scenario):

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

With this recipe, one run pairs a real, seeded database with an erroring
storage stub — the exact combination the current bundled-state model cannot
express.

---

## Decisions summary (resolved facts for implementation)

1. **Recipe schema.** JSON document with `schemaVersion: 1`, a `target` id, and
   a `bindings` map keyed by **parameter name**. Binding values: `"live"` /
   `{ "live": "<scenario>" }` / `{ "stub": "<name>", "with": {…} }` (shorthand
   `"stub:<name>"`) / `"default"` / `{ "value": <literal> }`; absent ⇒ default.
   Recipes live at `.shatter/recipes/<target-id>/<name>.json`.
2. **Stub authoring & registration.** Stubs are project-owned source under
   `shatter/stubs/<lang>/`, gated out of release builds, implementing the
   target parameter's **port trait** and exposing a factory. Discovery is a
   **config-declared registry** (`stubs:` in `.shatter/config.yaml`) mapping
   name → `implements` / `lang` / `source` / `factory`. Attribute-based
   auto-discovery is a future enhancement.
3. **Generator interface placement.** A **new generator shape** (the composed
   recipe generator) replaces the monolithic `State()` call *only when a recipe
   is attached*; `State()` is otherwise unchanged. It resolves each binding
   independently and assembles the argument tuple at the input-construction
   stage, after discovery and after recipe validation, before execution.
4. **Fallback behavior.** **Fail fast before the run** with a precise validation
   error when a named stub (or scenario, or port type) cannot be resolved.
   Never silently substitute a default for an explicitly named stub. Absent
   bindings (and explicit `"default"`) use default synthesis; that is the only
   default path.

## Out of scope for the follow-on implementation

- Authoring the port-trait refactor for any specific target (project-owned
  prerequisite; taxonomy `PROJECT-FIX`).
- Attribute/annotation-based stub auto-discovery (future enhancement).
- Generated knobs inside stubs beyond a `with` config object passed verbatim to
  the factory.
- Cross-target shared stub libraries / packaging.
