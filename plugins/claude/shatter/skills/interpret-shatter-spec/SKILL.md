---
name: interpret-shatter-spec
description: Explain a single Shatter spec JSON file in human terms — a short paragraph of overall interpretation plus 2-4 representative cases. Use for a quick read of one function's exploration result, not a full run review.
---

## Model Guidance

Recommended model: low. Single-file parsing and a brief narrative; no
multi-section report assembly.

## Purpose

Take one Shatter spec JSON file (the exploration result for a single
function) and produce a short markdown summary that a human can read in
under a minute.

This skill is deliberately lighter than `run-shatter` or
`report-shatter-issues`. Stay in the "single spec, short summary" lane:

- one spec file in
- one short markdown summary out
- no whole-run reviews, no enumerated issue reports, no cross-spec
  comparisons

## Required input

A path to a spec JSON file (typically `shatter-artifacts/<name>.spec.json`)
or the spec contents on stdin. If the user gave neither, ask for one.

## Procedure

1. Read the spec JSON. If it fails to parse, say so and stop — do not
   invent content.
2. Identify the target function's name and signature if present.
3. Walk the recorded cases. For each, note:
   - the concrete inputs
   - the observed output, return value, or thrown error
   - the path condition or constraint that selected this case, if recorded
4. Group cases by behavior: normal returns, boundary values, thrown
   errors, and any obviously degenerate or tool-failure cases.
5. Pick 2-4 cases that best represent the function's behavior. Prefer:
   - one typical happy-path case
   - one boundary or edge case
   - one error or exception case, if any
   - one additional case only if it shows distinct behavior
6. Distinguish program behavior from likely Shatter tool issues
   (timeouts, unresolved symbols, empty exploration). Call tool issues
   out separately so the reader does not mistake them for program
   semantics.

## Output shape

Print markdown to stdout with this shape, and nothing else:

```
# <function name or spec file name>

<one short paragraph, roughly 100-200 words total across the whole
output, describing what the function appears to do, which inputs it
splits on, and any notable boundary or error behavior>

## Representative cases

- **<short label>** — inputs: `<concrete input>`; result: `<output or
  error>`
- **<short label>** — inputs: `<concrete input>`; result: `<output or
  error>`
- (2-4 bullets total)

## Ambiguities

- <one bullet per obvious ambiguity, or the single line "None observed.">
```

Keep the whole document tight. If the spec is small, lean toward 2
cases. If a section would be empty, write `None observed.` rather than
omitting the heading.

## Schema reference

The spec JSON is the per-function artifact produced by a Shatter run.
The full review and report schema lives in the `run-shatter` skill's
references at `catalog/skills/run-shatter/references/report-schema.md`
inside this repository; downstream installs may not ship that file, so
the relevant case fields are summarized here:

- `Case`: a short label for the behavior
- `Representative sample`: one concrete input and the resulting output
  or thrown error
- `Why it matters`: plain-language impact (optional in this skill's
  summary)

This skill uses only the case shape (label + input + result). It does
not produce the full `Overall interpretation` / `Most important cases`
/ `Precise observed results` / `Possible issues or ambiguities` /
`Recommended next step` structure — that belongs to `run-shatter`'s
review output and `report-shatter-issues`' markdown report.

## Crate-bridge harness route annotation

When a spec was produced by a **crate-bridge** harness for a web-framework
handler (e.g. an axum handler), the generated driver `main.rs` mounts the
handler at a synthetic path such as `/test/{p0}/{p1}` rather than the
handler's real application route. The synthetic path loses the real
parameter names and bypasses per-route middleware, so a reader can be
misled about which inputs the handler actually splits on.

Whenever you generate or review a crate-bridge `main.rs` that contains a
synthetic `.route("/test/...")` call, annotate it so the real route is not
lost:

1. **Look up the real route.** Search the target project's router wiring —
   `build_router()` or the equivalent `Router::new()` / `.nest(...)` /
   `.route(...)` composition — for the entry that maps to the handler under
   test. Account for nested routers: a handler mounted via
   `Router::new().nest("/api", api)` has its real path prefixed by the nest
   path. Record the full path pattern, including its real parameter names.

2. **Add a `Real route:` comment immediately adjacent to the `.route()`
   call** (on the line directly above it), naming the resolved path. For the
   `create_bundle_entry` handler this is:

   ```rust
   // Real route: /workspaces/{workspace_id}/bundles/{bundle_id}/entries
   .route("/test/{p0}/{p1}", routing::any(/* handler */)) // TODO(shatter): replace synthetic path with real route above
   ```

3. **Add a `// TODO(shatter): replace synthetic path with real route above`
   annotation** on the synthetic `.route("/test/...")` line itself or on the
   line directly below it, so the mismatch is actionable.

Ideal (do this when the router is statically analyzable):

- Use the resolved real path pattern directly in the generated `.route()`
  call instead of the synthetic `/test/{p0}/{p1}`.
- Build the default seed URL from the real parameter names and plausible
  values (e.g. `/workspaces/ws_1/bundles/b_1/entries`) rather than synthetic
  `p0`/`p1` placeholders.

Regression requirement: if no matching route can be found for the handler,
still emit valid Rust. Keep the synthetic `.route("/test/...")` call, attach
the `// TODO(shatter): replace synthetic path with real route above`
annotation, and add a comment noting that no real route was resolved. Never
fail harness generation over a missing route.

## sqlx DATABASE_URL pre-flight check

When a harness drives a Rust **sqlx** target, the generated driver must
connect to a live PostgreSQL database before it can exercise the target. The
canonical sqlx integration-test idiom appears identically across such projects
and in Shatter's own generated generators:

```rust
let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
let pool = PgPoolOptions::new().max_connections(5).connect(&url).await.expect("connect");
MIGRATIONS.get_or_init(|| async { sqlx::migrate!("./migrations").run(&pool).await }).await;
```

Generated harnesses tend to degrade this into a hardcoded fallback such as

```rust
const DEFAULT_DATABASE_URL: &str = "postgres://user:pass@localhost:55432/db";
```

combined with `connect_lazy_with`. `connect_lazy_with` does not open a
connection eagerly: it defers the first connection attempt — and therefore the
failure when no database is listening — into the first fuzz iteration. The
reader then sees a connection error reported as if it were target behavior, and
the run wastes a full iteration discovering an environment problem.

Whenever you generate a sqlx harness `main.rs` (or the generator that produces
it), enforce a fail-fast database pre-flight **before** the fuzz loop is
entered:

1. **Require `DATABASE_URL` explicitly.** Do not silently fall back to a
   hardcoded localhost URL. Read the variable and, when it is unset or empty,
   emit an actionable error naming the problem, the fix, and the variable to
   set, then exit before the first iteration:

   ```rust
   let url = match std::env::var("DATABASE_URL") {
       Ok(u) if !u.is_empty() => u,
       _ => {
           eprintln!(
               "Error: DATABASE_URL is not set. Set it to a running Postgres \
                instance (e.g. run 'make api-test-integration') and re-run."
           );
           std::process::exit(1);
       }
   };
   ```

   Adapt the parenthetical command to the target project's documented
   integration-test entrypoint when one is discoverable (e.g. a `make` target,
   `task` command, or `docker compose` invocation); otherwise keep the generic
   `make api-test-integration` example.

2. **Replace `connect_lazy_with` with an eager connect (or a pre-flight
   connectivity check).** Use `PgPoolOptions::new().connect(&url).await` so a
   missing or unreachable database fails immediately with a clear message,
   rather than `connect_lazy_with`, which surfaces inside the fuzz loop:

   ```rust
   let pool = match PgPoolOptions::new().max_connections(5).connect(&url).await {
       Ok(p) => p,
       Err(e) => {
           eprintln!(
               "Error: could not connect to Postgres at DATABASE_URL: {e}. \
                Ensure a database is running (e.g. 'make api-test-integration')."
           );
           std::process::exit(1);
       }
   };
   ```

   Run `sqlx::migrate!()` against the eagerly connected pool before the first
   iteration so migration failures are also reported up front.

Ideal (managed Postgres mode — future enhancement): detect the
`PgPoolOptions + connect(DATABASE_URL) + sqlx::migrate!()` idiom and offer an
opt-in mode (CLI flag or config key, or auto-detection) that launches a
temporary Postgres container before the harness run — Docker primary,
Podman-compatible if feasible — exports `DATABASE_URL` into the harness process
environment, runs `sqlx::migrate!()` automatically before the first iteration,
and tears the container down after the run. Until that mode exists, the
fail-fast pre-flight above is the required behavior.

Regression requirement: never embed a hardcoded `DEFAULT_DATABASE_URL` fallback
and never use `connect_lazy_with` for the primary pool in a generated sqlx
harness. If the database setup cannot be resolved, still emit valid Rust that
exits early with the actionable error above — never defer the failure into the
fuzz loop.

## Out of scope

- Reviewing an entire Shatter run directory.
- Writing a durable markdown issue report (use `report-shatter-issues`).
- Comparing two spec files or diffing runs.
- Recommending fixes to the target program beyond noting ambiguities.
