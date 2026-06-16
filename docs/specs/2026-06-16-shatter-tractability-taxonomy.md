# Shatter Tractability Taxonomy

## Executive Summary

Shatter coverage rises when branch-bearing logic is separated from code that
Shatter cannot synthesize, execute, or observe. That is mostly ordinary
software design and testability advice: make dependencies explicit, keep pure
logic small, isolate effects, validate inputs at boundaries, and avoid hidden
global state. The Shatter-specific layer is deciding which testability patterns
matter most to an automated concolic harness.

Human tests can compensate for awkward code with hand-built fixtures, mocks,
custom constructors, and procedural setup. Shatter needs stronger regularity.
It must discover a target, construct inputs, invoke it without a live framework,
observe branch outcomes, and connect uncovered branches back to values it can
generate. A function can be unit-testable yet still be a weak Shatter target if
it accepts a rich service container, reads browser globals, opens a database,
or hides its useful decisions inside a callback passed to a framework factory.

The central recommendation is Gary Bernhardt's "Functional Core, Imperative
Shell" pattern: put decisions and transformations in a functional core over
plain data, and keep IO, framework lifecycle, mutation, logging, storage, and
network work in a thin imperative shell. The reference screencast is
<https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell>.
This document applies that idea to Shatter tractability across Go, TypeScript,
and Rust, using the existing `~/shatter-tractability-recommendations-engine.md`
note as seed material.

The intended future consumer is a `shatter-agents` skill or recommendations
engine. The engine should not simply repeat generic "write testable code"
advice. It should classify concrete Shatter signals, choose whether the right
answer is a project refactor, Shatter engine fix, configuration change, or
justified skip, and rank findings by leverage.
That ranking keeps guidance actionable instead of merely architectural.

## Core Principle: Functional Core, Imperative Shell

Shatter is a branch-logic coverage tool. Its best target is a function whose
inputs are synthesizable data and whose branches are visible in instrumented
source. Its worst target is a function whose branch-driving values are hidden
behind opaque handles, framework state, runtime globals, or uninstrumented
libraries.

Most tractability problems reduce to the same shape:

```text
framework/resource/input shell
  -> branch-bearing decisions
  -> framework/resource/output shell
```

If the decisions are still inside the shell, Shatter must synthesize the shell.
That means it may need an HTTP request, an Axum `State<AppState>`, an LSP
client, an initialized Zustand store, a database pool, a browser
`localStorage`, or a third-party decoder result before it can even reach the
domain logic. Sometimes a generator or execution adapter is the right answer.
Often the cheaper answer is to extract the domain decision into a plain data
function and leave the shell as a small integration surface.

The pattern is not a demand for purely functional programs. It is a local
refactoring rule:

- Put branching decisions over ordinary data in the core.
- Put IO, framework invocation, retry loops, logging, storage, telemetry, and
  cleanup in the shell.
- Represent effect outcomes as plain values before mapping them to responses.
- Treat the shell as either adapter-owned, fixture-driven, or a justified skip.

This is ordinary design guidance, but Shatter adds stricter acceptance
questions:

- Can Shatter construct the inputs without a live resource?
- Can Shatter call the target without owning a framework lifecycle?
- Are branch-driving values represented as plain data?
- Are external results modeled as values that can vary?
- Are uncovered branches in instrumented code, not hidden inside dependencies?
- Is the coverage denominator excluding lines that are intentionally pure IO?

## Tractability Gates

Every target passes through four gates before its coverage is useful.

### Constructibility

Constructibility asks whether Shatter can synthesize the target's parameters.
Plain strings, booleans, numbers, arrays, objects, enums, structs with known
fields, and JSON-like TypeScript shapes are good candidates. Opaque resources
are not.

Common constructibility blockers:

- Concrete external clients, pools, sockets, files, subprocesses, and framework
  context values.
- Rust, Go, or TypeScript types whose fields are outside the analyzed scope.
- Trait objects, function pointers, generic parameters without a chosen
  concrete type, and raw pointers.
- Domain types missing the serialization or deserialization traits required by
  the harness.
- By-reference or ownership shapes that the engine should adapt to centrally
  rather than forcing project-level wrappers.

The highest-leverage refactor is not "mock the whole app". It is usually
"accept the smallest behavior or data shape this function really needs".

### Executability

Executability asks whether the function runs after inputs are constructed.
Many functions build but fail immediately because they need live state:
`DATABASE_URL`, an HTTP server, an LSP subprocess, a browser API, a message
queue, credentials, or filesystem layout.

The project can respond in three ways:

- Provide deterministic setup or state factories when the live resource is part
  of the behavior worth exploring.
- Extract the logic after setup and before persistence into a pure core.
- Mark the resource shell as intentionally unsupported when it is only glue.

Executability also includes precondition failures. If most generated inputs
panic because a function assumes prior validation, make that precondition
explicit: validate first, return a result, or accept a validated newtype.

### Coverage Depth

Coverage depth asks whether Shatter reaches meaningful branches once the
target runs. Low depth can come from Shatter gaps or project shape.

Engine-shaped blockers include integer width and signedness loss, serde rename
mismatches, mutation that erodes required fields, and unsupported dispatch
forms. Project-shaped blockers include giant input surfaces, hidden dynamic
dispatch, branch guards inside third-party decoders, and state-machine behavior
that requires call sequences instead of one call.

Good refactors reduce the search surface and move exact branch guards into
instrumented code. For example, keep byte-header sniffing in project code even
if the full decoder is external; extract state transition functions from
store actions; split a handler into validation, authorization, and response
mapping helpers.

### Measurement

Measurement asks whether the reported coverage has an honest denominator. A
database-heavy handler may contain many lines that are pure IO statements.
After the happy path executes them once, more generated inputs cannot add much
coverage. A whole-file line coverage target can therefore punish code for
having an imperative shell even after branch logic is well covered.

Recommendations should separate:

- Branch-bearing project logic.
- Pure IO shell lines.
- External-library internals.
- Framework-generated or generated-code glue.
- Adapter-owned setup and teardown.

A future engine should emit a justified-skip register and an architectural
ceiling estimate: how much coverage is realistic before refactoring, and what
denominator should be used for branch-bearing code.

## Recommendation Dispositions

Every finding should carry a disposition. This prevents teams from refactoring
around Shatter bugs or waiting on engine work when a small project seam would
solve the problem.

`PROJECT-FIX` means the target project should change shape. Examples include
extracting a pure helper, adding a small interface, deriving `Deserialize`,
moving a framework call to the shell, or adding a deterministic scenario
factory.

`ENGINE-GAP` means Shatter should fix the class centrally. Examples include
Rust by-reference support, integer width and signedness, serde rename handling,
field-preserving mutation, cleaner dispatch failure reporting, or return
capture fallback for non-serializable values.

`CONFIG-TUNE` means the current project shape may be acceptable if Shatter is
configured better. Examples include longer budgets, lower parallelism, custom
generators, opaque type declarations, setup files, or execution profiles.

`JUSTIFIED-SKIP` means exclusion is the honest result. Examples include
generated code, framework glue with no branch-bearing decisions, C/FFI
internals, and live resource lifecycle code whose behavior belongs in an
integration test or adapter.

## Pattern Catalog

### Functional Core / Imperative Shell

Signal: a function mixes parsing, authorization, IO, decisions, and response
construction.

Sketch: extract functions such as `validate_request(input)`,
`authorize(actor, resource, action)`, `decide(snapshot, command)`, and
`map_outcome(outcome)` over plain data. Keep the original handler as an
imperative sequence.

Coverage benefit: Shatter can explore branch logic without database state,
network calls, framework extractors, or response writers.

Disposition: `PROJECT-FIX`, unless the shell needs an adapter because the
end-to-end resource behavior is the product.

### Small Project-Owned Ports Or Interfaces Around Opaque Resources

Signal: a function accepts a concrete client, pool, transport, or service
container but uses only one or two methods.

Sketch: define a minimal project-owned port such as `FileOpener`,
`SearchBackend`, `Clock`, `TokenValidator`, or `Storage`. Better yet, extract
the post-call decision over the returned data.

Coverage benefit: Shatter or ordinary tests can provide a small fake. The
opaque client lifecycle stays outside the tractable target.

Disposition: `PROJECT-FIX` for narrow ports, `JUSTIFIED-SKIP` for true handles,
and `ENGINE-GAP` only when Shatter should synthesize a common shape centrally.

### Handler Sandwich Split: Parse/Auth/Validate/Core/Effect/Render

Signal: HTTP, GraphQL, MCP, CLI, or worker handlers contain all behavior in one
body.

Sketch: split the sandwich into boundary parsing, authorization, validation,
core decision, effect execution, and response mapping. Make effect outcomes
plain enums or structs before rendering.

Coverage benefit: Shatter can cover validation, authorization decision, and
outcome mapping even when the live handler requires framework state.

Disposition: `PROJECT-FIX`.

### Query/Result Separation

Signal: SQL queries, row mapping, and decisions are interleaved.

Sketch: leave SQL in repository functions, map rows into plain snapshots, then
call pure functions over those snapshots. Represent not-found, conflict,
forbidden, and success as explicit values.

Coverage benefit: Shatter explores the branch logic without provisioning a
database. Scenario factories can still exercise the repository shell when
end-to-end confidence is needed.

Disposition: `PROJECT-FIX` plus optional `CONFIG-TUNE` for DB-backed scenarios.

### Scenario/State Factories For IO That Must Remain

Signal: a handler executes only with a live database, object store, or app
state, and pure extraction would lose important behavior.

Sketch: provide deterministic factories that seed one scenario per branch
family: missing row, wrong owner, validation failure, conflict, archived item,
and happy path. Keep the spread replayable.

Coverage benefit: Shatter can cover more than a happy path without inventing
database state from scratch.

Disposition: `PROJECT-FIX` when the project owns fixtures, often paired with
`ENGINE-GAP` if Shatter lacks the adapter wiring to consume them.

### Fixture Sets Across External Decoder Or FFI Boundaries

Signal: branches after image, archive, compression, crypto, parser, or C/FFI
calls remain uncovered.

Sketch: keep project-owned guard and classification code separate, then seed a
small set of valid, edge, and corrupt fixtures that cross the external
boundary. Do not treat dependency internals as project coverage.

Coverage benefit: project branches downstream of the external call become
reachable while the dependency itself remains a justified skip.

Disposition: `PROJECT-FIX` for fixtures and guard extraction,
`JUSTIFIED-SKIP` for dependency internals.

### Time/Random/Env/Global Extraction

Signal: logic reads `time.Now`, random IDs, environment variables, process
state, global singletons, or feature flags directly.

Sketch: pass a clock, ID generator, configuration value, or feature snapshot
into the pure core. In TypeScript, inject storage and fetch-like functions
instead of reading globals where decisions happen.

Coverage benefit: Shatter can vary the branch-driving value directly and avoid
non-deterministic executions.

Disposition: `PROJECT-FIX`.

### Browser/Runtime Global Isolation

Signal: TypeScript logic mixes decisions with `window`, `document`,
`localStorage`, `sessionStorage`, timers, or `fetch`.

Sketch: isolate global reads and writes in shell helpers. Convert persisted
state into plain data before calling state-transition logic. Model fetch
responses as values before mapping them into UI state.

Coverage benefit: Shatter can run the decision logic in a Node or VM harness
without needing a full browser runtime.

Disposition: `PROJECT-FIX`, or `CONFIG-TUNE` if an existing setup file already
provides faithful globals.

### Factory And Closure Capture For Stores/Builders/Registries

Signal: useful methods are not exported functions; they are returned from a
factory callback, closure, plugin registry, command builder, or Zustand store.

Sketch: extract state transition helpers that accept `(state, command)` and
return a next state or effect plan. If extraction is not desired, a future
factory-capture adapter can discover returned methods and explore bounded
method sequences.

Coverage benefit: direct helper extraction gives immediate coverage; factory
capture is a future Shatter capability for cases where the source shape should
stay intact.

Disposition: `PROJECT-FIX` for helper extraction, `ENGINE-GAP` for generic
factory capture, `CONFIG-TUNE` for library-specific adapters.

### Callback And Streaming Inversion

Signal: external APIs call project code through callbacks, writers, emitters,
or streaming functions.

Sketch: move chunk classification and state update logic into functions that
accept plain events or deltas. Keep the callback only as an adapter that feeds
events to the core.

Coverage benefit: Shatter can synthesize event sequences without running the
external streaming provider.

Disposition: `PROJECT-FIX`.

### Concurrency Shell Extraction

Signal: goroutines, channels, timers, async tasks, or workers contain branch
logic mixed with scheduling.

Sketch: extract a planning function such as `plan_retries(now, snapshot,
config) -> Plan`. Let the concurrent shell apply the plan.

Coverage benefit: scheduling and wall-clock behavior stay out of scope while
retry, batching, timeout, and abandonment decisions become tractable.

Disposition: `PROJECT-FIX` for the planning seam, `JUSTIFIED-SKIP` for the
scheduler shell when it has no independent branch logic.

### Generated/Framework Glue Avoidance

Signal: targets live in generated files, framework dispatch tables, resolver
boilerplate, or route glue.

Sketch: move project decisions into hand-written helpers. Treat generated
dispatch as an adapter or skip surface.

Coverage benefit: Shatter spends budget on durable project logic instead of
machine-generated code that will be overwritten.

Disposition: `JUSTIFIED-SKIP` for generated code and `PROJECT-FIX` when logic
has drifted into glue.

### Serialization And Validated-Input Boundaries

Signal: generated values fail deserialization, panic on implicit preconditions,
or miss fields because internal and wire shapes differ.

Sketch: make validation explicit and return structured errors. Derive needed
serialization traits for domain types that are legitimate Shatter inputs.
Preserve serde or JSON wire names in the analyzer when the engine owns the
gap.

Coverage benefit: Shatter can distinguish valid-input behavior from validator
behavior instead of spending iterations on invalid objects.

Disposition: `PROJECT-FIX` for derives and validation seams, `ENGINE-GAP` for
serde rename and mutation repair classes.

## Example Mapping

`~/project/refute/internal/backend/lsp/priming.go` has `PrimeWorkspace(client
*Client, root, languageID string)`. The interesting decisions are directory
skips, maximum opened files, extension-to-language mapping, and ignoring failed
opens. The concrete LSP client is an opaque subprocess-backed resource. A
small `DidOpen(path, languageID) error` port, or an extracted planning function
that returns files to open, would expose the core behavior. This is primarily
`PROJECT-FIX`; the live client lifecycle remains adapter territory or a
`JUSTIFIED-SKIP`.

`~/project/flotsam/api/internal/mcp/tools.go` shows two useful shapes.
`doSearch` tries embedding plus semantic search and falls back to full-text
search on errors or empty semantic results. The branch-driving data is the
embedding outcome and search result cardinality, not the live provider itself.
`doGoogleSearch` fans out to Drive and Gmail through an `*http.Client`, logs
errors, and merges result DTOs. The recommendation is to keep external calls
behind ports and extract result selection/merge logic over plain outcomes.
This is `PROJECT-FIX`, with stateful provider setup left to integration tests.

`~/project/kapow/api/internal/nl/handler.go` has `NewHandlerWithPreprocessor`,
which decodes HTTP, normalizes a surface value, emits observability events,
sets a timeout, calls `ConvertQuestionWithPreprocessor`, classifies errors,
logs, and writes JSON. Some pure seams already exist, such as surface
normalization and error classification. The handler sandwich split would make
request validation, conversion outcome classification, and response mapping
more directly explorable. This is a high-leverage `PROJECT-FIX`.

`~/project/kapow/web/src/stores/fitSessionStore.ts` is a TypeScript Zustand
store. It contains plain data types and helpers, but also `localStorage`,
per-tab persistence, GraphQL client calls, telemetry, and stateful store
actions behind a factory callback. The Shatter-friendly path is to extract
state transitions and persistence parsing into plain functions over
`FitSessionData`, while leaving Zustand and browser storage in the shell. A
future `ENGINE-GAP` could add factory-capture exploration for returned store
methods, but project-side extraction gives clearer coverage today.

`~/project/pickpackit/web/src/features/trips/tripFilters.ts` is the positive
example. `applyTripFilters`, `hasActiveTripPredicates`, and `todayIso` operate
on plain arrays, dates, strings, and filter state. There is no network,
browser storage, framework lifecycle, or hidden client. It demonstrates the
functional core target shape that Shatter should reward.

`~/project/pickpackit/api/src/handlers/tags.rs` illustrates a Rust
Axum/sqlx shell. Handlers accept `State<AppState>`, `CurrentAccount`, `Path`,
and `Json` extractors; they call role checks, trim and validate values, run
SQL queries through `PgPool`, and map rows to `Json`. Helpers such as
`require_trimmed`, `optional_trimmed`, and `resolve_tag_source` are already
small cores. More behavior could be extracted into plain request validation,
authorization outcome classification, and database outcome mapping. The
database shell can use scenario factories where end-to-end coverage matters.

The seed note `~/shatter-tractability-recommendations-engine.md` adds
observed Rust/Axum/sqlx blocker classes: missing serde derives,
non-serializable returns, sized integer generation, serde rename handling,
field erosion during mutation, external/FFI boundaries, and denominator
inflation from pure IO lines. These are not all project refactors. Several
are `ENGINE-GAP` findings that Shatter should fix once rather than asking
every target project to reshape around them.

## Future Recommendations Engine

A future `shatter-agents` engine should consume Shatter scan/explore output,
source facts, and lightweight static signals. It should emit two tracks:

- Engine track: recurring Shatter gaps that should become Shatter issues.
- Project track: refactors, generators, fixtures, config, or justified skips
  that belong in the target project.

Suggested finding schema:

```text
pattern_id: stable taxonomy key
tractability_gate: constructibility | executability | coverage_depth | measurement
disposition: PROJECT-FIX | ENGINE-GAP | CONFIG-TUNE | JUSTIFIED-SKIP
confidence: low | medium | high
evidence: file, symbol, Shatter outcome, reason string, or static signal
suggested_refactor: bounded pattern sketch
expected_coverage_gain: local | family | tier | corpus
leverage_score: rough impact divided by effort
effort_estimate: trivial | small | structural | adapter-sized
manual_review_notes: caveats and semantic risks
engine_issue_ref: optional Shatter issue or proposed issue key
```

Initial rules can be simple:

- `unsupported` plus opaque parameter signal maps to constructibility.
- `error_only` plus connection, environment, or timeout setup failure maps to
  executability.
- Low branch coverage plus byte/parser/external-library shape maps to coverage
  depth.
- High IO-line fraction in handlers maps to measurement and functional-core
  recommendations.
- Repeated serde, integer, mutation, or dispatch reasons across many targets
  map to `ENGINE-GAP` with high leverage.

The engine should never claim that a refactor is automatically safe. It should
propose a tractability seam and explain why the seam helps Shatter. The user or
implementing agent still owns semantic preservation.

## Non-Goals

This document does not define an analyzer CLI, create a skill, edit generated
plugin output, or change Shatter core. It does not prescribe exact automated
Refute operations. It does not require target projects to adopt every pattern.
It does not attempt to make all code directly explorable; live lifecycle code,
framework glue, generated code, and external-library internals often remain
legitimate skips.

The goal is a shared vocabulary for deciding whether low coverage is caused by
project shape, Shatter configuration, an engine gap, or an honest boundary.
