# Technical Brainstorm: DynamoDB Native Vector Search Support

> Status: **Phase 4 complete.** User clarifications parsed (Q1–Q6). Approaches, SWOT,
> recommendation, risks, and a phased execution plan are below.

## Decisions Locked from Clarifications

| Q | Decision |
|---|----------|
| Q1 | Dedicated `@c.vector_index(...)` decorator, stacked above `@c.model` like GSIs. |
| Q2 | Generated `search(...)` returns a `SearchResults` type (item + score); named kwargs generated from the SearchSchema; embedding **not** stripped. |
| Q3 | Emit a `vectorindices` block into the EasySAM dict as if supported; EasySAM CFN support coordinated separately. |
| Q4 | **Option A** — add `get_client()` to the `DynamoAccess` ABC and `DefaultDynamoAccess`. |
| Q5 | Vectors as `numpy.ndarray`, gated behind an optional `prismarine[vectors]` extra; core stays numpy-free. |
| Q6 | Backfill/readiness is **out of library scope** — documented only, no retry/wait helper. |

> **Discrepancy note (Q4 × Q5):** `search_vectors` needs a plain `[{"N": str(x)}]` payload
> (no `L` wrapper) and numpy arrays are not Decimal/JSON-native. The vector formatter must
> live behind the optional-extra boundary (guarded `import numpy`) so the *core* runtime
> and the default `typed-dict`/`pydantic` code paths never hard-depend on numpy. The
> generated client must import the vector helper lazily/optionally. This is the main
> design tension and is addressed in every approach below.

## Problem Statement & Scope

- **Core Objective:** Extend Prismarine so that models can declare a DynamoDB *native
  vector index* (launched Aug 2026), and the generated client exposes a type-safe
  similarity-search method (`SearchVectors`) alongside the existing CRUD surface.
- **Scope Boundaries:**
  - **IN:** A `Cluster` decorator (or `model`/`index` extension) to declare a vector
    index; generation of a search method in `prismarine_client.py`; a runtime helper
    wrapping the boto3 `search_vectors` client call; EasySAM CloudFormation emission of
    `VectorIndexes` on the table; docs/tests.
  - **OUT:** Generating embeddings (Prismarine stores/searches vectors; the caller
    produces them via Bedrock/Cohere/etc.); re-embedding stale content; managing
    backfill/readiness orchestration beyond documenting it; changing the existing
    GSI (`index`) semantics.
- **Key Constraints:**
  - `SearchVectors` is a **client-level** boto3 call (`client.search_vectors(...)`),
    **not** a resource/`Table` method. Prismarine's runtime (`DynamoAccess`) currently
    exposes only `get_resource()` and `get_table()` (the resource layer). A new access
    path is required.
  - Vector indexes require the table to be **on-demand** (`PAY_PER_REQUEST`).
  - Indexes cannot be searched while **backfilling** (`ValidationException`), and a
    newly-`ACTIVE` index has a brief non-searchable window — searches must be
    retry-tolerant.
  - `SearchVector` is a **plain list** of `{"N": ...}` (not an `L`-wrapped attribute).
  - The stored embedding attribute is an `L` of `N` (list of numbers). Note the runtime
    `serialize_item`/`prepare_item` helpers already convert `float`↔`Decimal`, which
    matters for storing/reading vectors.
  - Backwards compatibility: `typed-dict` (default) and `pydantic` model libraries must
    both keep working; models without a vector index must generate identical output.
  - Per-table limit of 5 vector indexes; only one index create/delete in flight at a time.

## Technical Baseline & External Research

### Current Architecture (local audit)

- **`runtime/cluster.py`** — `Cluster` holds `models`/`exports`. `@c.model(...)`
  records `{cls, main:{PK,SK}, table, indexes:{}, class_name, name, trigger?, ttl?}`.
  `@c.index(index=, PK=, SK=)` adds to `model['indexes']`. Decorators are the natural
  extension point; a vector index would be a new decorator or a new field on an
  existing one.
- **`prisma_client.py`** — `build_client()` renders `model.mako` per model, passing
  `Indexes=[{name, PartitionKey, SortKey}]`. Emits a header with runtime imports
  (`_query`, `_get_item`, `_update`, `_put_item`, `_delete`, `_scan`, `_save`, ...).
  A new `_search_vectors` import + a new template block would be the generation change.
  Output is `ruff format`ted.
- **`model.mako`** — Renders `Model` subclass with `list/get/put/update/save/delete/scan`
  and a nested class per GSI (`class ByBar: ... list/get`). A vector search method would
  be a new top-level static method and/or a nested class mirroring the GSI pattern.
- **`runtime/dynamo_crud.py`** — CRUD helpers operate on `dynamo.get_table(table)`
  (resource `Table`). `serialize_item` converts `int`/`float`→`Decimal`; `prepare_item`
  converts back. **`search_vectors` is not available on `Table`** — it lives on the
  low-level client, so a new helper + access method is required.
- **`runtime/dynamo_access.py`** — Abstract `DynamoAccess` with `get_resource()` /
  `get_table()`. **No client accessor.** `runtime/dynamo_default.py` implements it via
  `boto3.resource('dynamodb')`. To call `search_vectors` we need `boto3.client('dynamodb')`
  (or `resource.meta.client`).
- **`prisma_easysam.py`** — `build_dynamo_tables()` maps models → EasySAM table defs
  (`attributes`, `indices`, `trigger`, `ttl`). A vector index would add a new key
  (e.g. `vectorindices`) that EasySAM must translate to `VectorIndexes` in CloudFormation.
  **EasySAM support for `VectorIndexes` is an external dependency and may not exist yet.**
- **`tests/test_prisma_client_generation.py`** — Existing generation tests are the
  model to follow for verifying new template output.

### State of the Art / Industry Standards

- **DynamoDB native vector search** (GA Aug 4–5, 2026): vector embeddings stored
  alongside operational data; `SearchVectors` API; no separate vector DB / replication
  pipeline. SDK/CLI support added in the Aug 4 2026 service model update.
- **Create/manage** via `CreateTable --vector-indexes` or `UpdateTable
  --vector-index-updates` (control plane, standard endpoint).
- **Search** via `search_vectors` (dedicated search endpoint, auto-routed by the SDK).
- **Index shape:** `VectorAttribute.AttributeName`, `Dimensions` (≤4096; common
  384/768/1024/1536/3072), `DistanceFunction` (`COSINE`|`EUCLIDEAN`|`DOT_PRODUCT`),
  optional `SearchSchema` (a `HASH` partition-key element + `INLINE_FILTER` elements),
  `Projection`.
- **Search request:** `TableName`, `IndexName`, `SearchVector` (plain `[{"N":..}]`),
  `TopK`, optional `SearchConditionExpression` + `ExpressionAttributeValues`/`Names`,
  optional `ProjectionExpression`. Response: `SearchResults[] = {Item, Score}`.
- **Distance/score semantics:** `COSINE`/`EUCLIDEAN` → lower score = more similar;
  `DOT_PRODUCT` → higher score = more similar.
- **Constraints:** on-demand only; equality-only for `HASH` in `SearchConditionExpression`;
  comparison/range allowed for `INLINE_FILTER`; missing `HASH` attr silently
  de-indexes an item; vectors excluded from results unless requested via projection.

### Relevant Ecosystem Options

- **boto3** `DynamoDB.Client.search_vectors` — the canonical call. Requires the client
  layer, which Prismarine does not currently expose.
- **EasySAM** (`build_dynamo_tables` consumer) — must learn to emit `VectorIndexes`.
  This is the primary external unknown for the infra/emission path.
- **Embedding providers** (Bedrock Titan, Cohere) — out of scope for Prismarine, but the
  docs/examples should point users to them.

## Open Questions & User Clarifications

#### Q1: Declaration API — new decorator vs. extend `model`/`index`?
- **Context:** GSIs use `@c.index(index=, PK=, SK=)` stacked above `@c.model`. A vector
  index has a very different shape (`vector_attribute`, `dimensions`, `distance`,
  optional `search_schema` of HASH + inline filters). Options: (a) a dedicated
  `@c.vector_index(index=, attribute=, dimensions=, distance=, hash=?, filters=[]?)`
  decorator, or (b) a `vector=` kwarg on `@c.model`, or (c) reuse `@c.index(..., vector={...})`.
  A dedicated decorator keeps concerns separate and mirrors the existing pattern best.
- **User Input:**
    <!-- USER_INPUT_START:Q1 -->
    Dedicated decorator `@c.vector_index` seems appropriate
    <!-- USER_INPUT_END:Q1 -->

#### Q2: Generated search method — signature and shape?
- **Context:** Proposed nested-class mirroring GSIs, e.g.
  `TeamModel.ByEmbedding.search(*, vector: list[float], top_k: int = 10,
  <hash_key>: str, <filter>: ... = None, projection: list[str] | None = None)
  -> list[tuple[Team, float]]`. Open points: (a) return `list[tuple[Model, score]]`
  vs. a `SearchResult` dataclass/TypedDict with `item` + `score`; (b) whether to expose
  raw `SearchConditionExpression` or generate named kwargs from the SearchSchema
  (typed, IDE-friendly — consistent with Prismarine's "named args" philosophy);
  (c) whether to auto-strip the embedding attribute from returned models.
- **User Input:**
    <!-- USER_INPUT_START:Q2 -->
    Return `SearchResults`. Generate named kwargs. No need to strip.
    <!-- USER_INPUT_END:Q2 -->

#### Q3: Infrastructure / EasySAM emission — in scope for this iteration?
- **Context:** `search_vectors` (runtime) and table provisioning (`VectorIndexes` in
  CloudFormation via EasySAM) are separable. EasySAM may not yet support `VectorIndexes`.
  Options: (a) full stack now (blocked on EasySAM feature); (b) runtime + generation
  now, emit a `vectorindices` block into the EasySAM dict and coordinate the EasySAM
  change separately; (c) runtime + generation only, users provision the index manually
  (CLI/console) for now.
- **User Input:**
    <!-- USER_INPUT_START:Q3 -->
    Emit `vectorindices` block into EasySAM dict, as if it was defined. We will coordinate the required EasySAM updates.
    flexible and
    <!-- USER_INPUT_END:Q3 -->

#### Q4: Runtime client access — how should Prismarine reach the low-level client?
- **Context:** `search_vectors` is a client call. `DynamoAccess` exposes only
  resource/`Table`. Options: (a) add `get_client()` to the `DynamoAccess` ABC and
  `DefaultDynamoAccess` (`boto3.client('dynamodb')`); (b) derive it lazily from
  `resource.meta.client` inside a new `_search_vectors` helper without touching the ABC.
  Option (a) is cleaner and testable but changes the public `DynamoAccess` contract,
  affecting custom-access implementations (see `example/myapp-custom-access`).
- **User Input:**
    <!-- USER_INPUT_START:Q4 -->
    Option A.
    <!-- USER_INPUT_END:Q4 -->

#### Q5: Vector value typing and (de)serialization?
- **Context:** Stored vectors are `L` of `N`; the runtime's `serialize_item` converts
  `float`→`Decimal(str(v))` and `prepare_item` converts back to `float`. For `put`/`update`
  of large 1536-dim vectors this is a per-element conversion. For `search_vectors` the
  `SearchVector` must be a plain `[{"N": "..."}]` list (no `L` wrapper), which bypasses
  the resource serializer entirely and needs its own formatter. Question: is the existing
  Decimal round-trip acceptable for vector attributes, and should the query vector accept
  `list[float]` (Prismarine formats it) — assumed yes?
- **User Input:**
    <!-- USER_INPUT_START:Q5 -->
    I would prefer `numpy.array` for the vector values. We may also consider using a optional capability, such as `primarine[vectors]` to be more flexible with dependencies.
    <!-- USER_INPUT_END:Q5 -->

#### Q6: Readiness / backfill handling?
- **Context:** Searches fail with `ValidationException` while backfilling and briefly
  after `ACTIVE`. Options: (a) do nothing, document it, let callers retry; (b) add an
  optional retry wrapper in the runtime helper; (c) provide a `wait_until_searchable`
  helper. Minimal scope = (a).
- **User Input:**
    <!-- USER_INPUT_START:Q6 -->
    OPtion A - out of library scope.
    <!-- USER_INPUT_END:Q6 -->

### Baseline Assumptions (if left default)

1. **Q1:** Dedicated `@c.vector_index(...)` decorator, stacked above `@c.model` like GSIs.
2. **Q2:** Nested class per vector index (`Team Model.<Name>.search(...)`), typed named
   kwargs generated from the SearchSchema, returns a list of `(Model, score)` tuples with
   the embedding attribute excluded by default.
3. **Q3:** Runtime + client generation this iteration; emit a `vectorindices` block into
   the EasySAM dict but treat actual EasySAM CloudFormation support as a coordinated,
   separate change (documented as "requires EasySAM ≥ X").
4. **Q4:** Add `get_client()` to `DynamoAccess` + `DefaultDynamoAccess`, with a default
   implementation deriving from `resource.meta.client` so existing custom-access classes
   keep working without changes.
5. **Q5:** Query vector accepts `list[float]`; Prismarine formats it to the plain
   `[{"N": str(x)}]` shape; stored-vector Decimal round-trip is left as-is.
6. **Q6:** Document the backfill/readiness caveat; no automatic retry in v1.

---

## Architectural Approaches Evaluated

All approaches share the same locked decisions (dedicated decorator, `SearchResults`
return, named kwargs, `get_client()`, numpy-optional, no readiness helper). They differ
in **how the numpy-optional boundary and the generated search code are structured** —
the one real remaining degree of freedom.

Shared building blocks (common to A/B/C):
- **`cluster.py`:** `@c.vector_index(index, attribute, dimensions, distance='COSINE',
  hash=None, filters=[], projection='ALL')` → records
  `model['vector_indexes'][index] = {...}`. Requires the model decorator below it
  (same guard as `@c.index`). Validates `distance ∈ {COSINE,EUCLIDEAN,DOT_PRODUCT}`,
  `1 ≤ dimensions ≤ 4096`, `len(model['vector_indexes']) ≤ 5`.
- **`dynamo_access.py` / `dynamo_default.py`:** add `get_client()` to the ABC;
  default implementation returns `self.get_resource().meta.client` so existing custom
  `DynamoAccess` subclasses keep working without edits (they inherit the default).
- **`SearchResults`:** a runtime type exported from `prismarine.runtime`. A generic
  container: `SearchResult(item: Model, score: float)` + `SearchResults` as
  `list[SearchResult]` (or a small wrapper with `.items()`/iteration). Generated per
  model so `item` is typed to the concrete model.
- **`prisma_easysam.py`:** emit `result[short_name]['vectorindices']` from
  `model['vector_indexes']` (attribute, dimensions, distancefunction, searchschema).
- **Docs/tests:** README section, `example/` model with a vector index, generation test
  asserting the emitted method + a `vectorindices` easysam assertion.

### Approach A: Runtime-Isolated Vector Module (numpy behind a single seam)

- **Concept:** All numpy/vector-formatting logic lives in **one new runtime module**
  `runtime/dynamo_vectors.py` with `_search_vectors(dynamo, table, index, *, vector,
  top_k, condition=None, expr_values=None, projection=None) -> SearchResults`. numpy is
  imported **lazily inside that module** (guarded: accept `numpy.ndarray` *or* any
  sequence, call `.tolist()` when present, else `list(...)`, then format to
  `[{"N": repr(float(x))}]`). The generated client imports `_search_vectors` only when a
  model actually declares a vector index. Core CRUD (`dynamo_crud.py`) is untouched.
- **Component Changes:** `cluster.py` (+decorator), `dynamo_access.py`/`dynamo_default.py`
  (+`get_client`), **new** `runtime/dynamo_vectors.py`, `runtime/__init__.py`
  (export `SearchResult`/`SearchResults`), `model.mako` (+search block, nested class per
  vector index), `prisma_client.py` (conditional `_search_vectors` import + render vector
  indexes), `prisma_easysam.py` (+`vectorindices`), `pyproject.toml`
  (`[project.optional-dependencies] vectors = ["numpy>=..."]`).
- **Dependencies Introduced:** `numpy` (optional extra only).

### Approach B: Inline in `dynamo_crud.py` with runtime numpy guard

- **Concept:** Add `_search_vectors` directly into the existing `dynamo_crud.py`
  alongside the other `_`-helpers, with an inline `try: import numpy` guard at call time.
  Fewer files; consistent with "all helpers in one module." Downside: mixes an
  optional-dependency code path into the core CRUD module that every generated client
  imports, so the numpy seam is less contained and easier to accidentally harden into a
  real dependency.
- **Component Changes:** Same as A but *without* the new module — logic folded into
  `dynamo_crud.py`.
- **Dependencies Introduced:** `numpy` (optional extra), but the guard sits in the core
  module.

### Approach C: Vector formatting in generated client + thin runtime call

- **Concept:** Push vector→`[{"N":...}]` formatting into the **generated client code**
  (emitted by the template), leaving the runtime helper a thin `client.search_vectors`
  passthrough. Maximizes "explicit generated code" visibility. Downside: numpy handling
  and float formatting get duplicated into every generated client and are hard to fix
  centrally after generation; conflicts with keeping generated files
  regeneration-only and thin.
- **Component Changes:** Heavier `model.mako`; minimal runtime helper; same decorator/
  access/easysam changes.
- **Dependencies Introduced:** `numpy` (optional extra), referenced from generated code.

## Structured Comparison & Methodology

### SWOT Matrix

| Approach | Strengths | Weaknesses | Opportunities | Threats/Risks |
|---|---|---|---|---|
| **A: Isolated module** | Single, contained numpy seam; core CRUD untouched; easy to test in isolation; lazy import means non-vector clients never touch numpy | One more file; slight indirection | Clean home for future vector features (batch search, wait-helpers if scope changes) | Minimal — mainly getting the lazy-import guard right |
| **B: Inline in crud** | Fewest files; all helpers co-located | Optional-dep path lives in the module every client imports; higher risk of numpy hardening into a hard dep; harder to keep core numpy-free | — | Accidental `import numpy` at module top breaks core installs without the extra |
| **C: Formatting in template** | Very explicit generated code | Logic duplicated across generated clients; central fixes require regen; fattens template; numpy leaks into generated import graph | — | Divergent generated clients; regressions hard to patch post-generation |

### Methodology notes
- Weighted by Prismarine's existing conventions: **thin generated files**, **runtime
  helpers do the work**, **optional features stay optional** (mirrors how `pydantic`
  support is gated). Approach A aligns with all three; B weakens the optional boundary;
  C weakens the thin-generated-file principle.

## Recommendation

**Adopt Approach A — the runtime-isolated vector module.**

Rationale:
- **Keeps the numpy boundary in exactly one place.** The Q5 requirement (numpy behind
  `prismarine[vectors]`) is only safe if numpy is never imported at the top of a module
  that the core/every client loads. A dedicated `runtime/dynamo_vectors.py` with a lazy,
  duck-typed import (`.tolist()` when available, else `list(...)`) is the cleanest
  enforcement and matches the established pattern used for the optional pydantic path.
- **Preserves the thin-generated-client principle.** The generated client only imports
  and calls `_search_vectors`; all formatting/score logic stays centrally patchable
  (rejects C).
- **Doesn't contaminate core CRUD.** Every generated client imports `dynamo_crud`;
  folding an optional-dep path there (B) invites accidental hard-dependency regressions.
- **Testable:** the module can be unit-tested with a fake client and both a numpy array
  and a plain list, proving the optional boundary works with and without numpy installed.

The `get_client()` addition (Q4/Option A) with a `resource.meta.client` default keeps
the `DynamoAccess` contract backward-compatible for `example/myapp-custom-access`-style
subclasses. `SearchResults` (Q2) is generated per-model for typed `item` access.

### Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| numpy accidentally becomes a hard dependency | Confine all numpy references to `runtime/dynamo_vectors.py` behind a lazy import; add a test that imports the core + a non-vector generated client with numpy uninstalled (or simulated absent) |
| `search_vectors` unavailable in the pinned boto3 (needs Aug-2026 service model) | Bump/verify the minimum boto3 in `pyproject.toml`; surface a clear error if `get_client()` lacks `search_vectors` |
| EasySAM can't yet consume `vectorindices` | Per Q3, emit the block regardless and document "requires EasySAM ≥ X"; coordinate the EasySAM change separately; keep the key name agreed with EasySAM maintainers |
| Score-direction confusion (COSINE/EUCLIDEAN lower-is-better vs DOT_PRODUCT higher) | Return the raw `Score` in `SearchResults` and document semantics per distance function; do not silently re-sort or invert |
| `SearchConditionExpression` requires HASH value when SearchSchema defines one | Generate the HASH kwarg as **required** (non-defaulted) when a schema HASH exists; inline filters as optional kwargs; equality-only for HASH |
| Decimal round-trip cost / precision on stored 1536-dim vectors | Out of scope for search path (search uses plain-N formatting); document f32 precision note; leave stored-attribute serialization unchanged |
| Backfilling / newly-ACTIVE `ValidationException` | Out of scope per Q6 — document the caveat and that callers must retry |

### Summary Table

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Declaration | `@c.vector_index(...)` decorator | Q1; mirrors `@c.index` stacking |
| Return type | Per-model `SearchResults` (item + score) | Q2; typed, keeps score |
| Filter args | Named kwargs from SearchSchema (HASH required, filters optional) | Q2; matches named-arg philosophy |
| Client access | `get_client()` on ABC + default via `resource.meta.client` | Q4/Option A; backward compatible |
| Vectors | `numpy.ndarray` (duck-typed), optional `prismarine[vectors]` | Q5; core stays numpy-free |
| Code placement | Isolated `runtime/dynamo_vectors.py` (Approach A) | Contains numpy seam; thin generated client; core untouched |
| Infra | Emit `vectorindices` into EasySAM dict | Q3; coordinate EasySAM separately |
| Readiness | Document only | Q6; out of scope |

## Phased Execution Plan

1. **Decorator + model data (`cluster.py`)** — add `@c.vector_index`, validation, and
   `model['vector_indexes']`. Unit-test the decorator records/validates correctly.
2. **Runtime access (`dynamo_access.py`, `dynamo_default.py`)** — add `get_client()` to
   the ABC with a `resource.meta.client` default; confirm custom-access example still
   satisfies the interface.
3. **Vector runtime module (`runtime/dynamo_vectors.py`)** — `_search_vectors(...)` +
   `SearchResult`/`SearchResults`; lazy numpy import; format vector to `[{"N": ...}]`;
   build `SearchConditionExpression`/`ExpressionAttributeValues` from kwargs; map
   response `SearchResults` → typed results. Export types from `runtime/__init__.py`.
4. **Generation (`model.mako`, `prisma_client.py`)** — render a nested class per vector
   index with `search(*, vector, top_k=10, <hash> [required], <filter>=None,
   projection=None)`; conditionally import `_search_vectors`/`SearchResults`; support both
   `typed-dict` and `pydantic` model libraries.
5. **EasySAM emission (`prisma_easysam.py`)** — emit `vectorindices` from
   `model['vector_indexes']`.
6. **Packaging (`pyproject.toml`)** — add `vectors = ["numpy>=..."]` optional extra;
   verify/raise minimum boto3 for `search_vectors`.
7. **Tests** — extend `tests/test_prisma_client_generation.py` for the emitted search
   method and `vectorindices`; add a runtime test for `_search_vectors` with a fake
   client using both a numpy array and a plain list; add a "numpy-absent" import test.
8. **Docs + example** — README `vector_index` section (declaration, search usage, score
   semantics, backfill caveat, `pip install prismarine[vectors]`); add a vector model to
   `example/`.

Ready to convert this into a seed (`Seed`) or a full spec (`Save Spec` / `Split Tasks`)
on request.
