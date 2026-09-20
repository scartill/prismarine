# Technical Brainstorm: DynamoDB Native Vector Search Support

> Status: **Phase 2 — awaiting user clarifications.** Approaches and recommendation
> (Phases 3–4) will be filled in after the `USER_INPUT` placeholders below are answered.

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

_Pending — filled in Phase 3 after clarifications._

## Structured Comparison & Methodology

_Pending — filled in Phase 3._

## Recommendation

_Pending — filled in Phase 4._
