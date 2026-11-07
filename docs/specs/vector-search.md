---
generated-by: "Plan Spec"
source: docs/seed/vector-search.md
generated-at: 2026-10-31T10:40:00+02:00
status: finalized
critiqued-revision: 0f625db
---

# Spec: DynamoDB Native Vector Search Support

_Derived from `docs/seed/vector-search.md`. Design decisions confirmed with the user
(numbered Q&A: 1-b, 2-a, 3-a, 4-a, 5-c, 6-a)._

_Pass-1 critique (`docs/critiques/vector-search.md`) applied: E1 (TypeSerializer for
low-level values), P1 (reserved-keyword validation), X1 (consumed_capacity), E2 (pre-flight
finite/dimension validation), E3 (namespaced condition placeholders), P2 (schema-derived
filter type hints)._

_Pass-2 critique (`docs/critiques/vector-search-pass2.md`) applied: X1 (removed hallucinated
`next_token` — `SearchVectors` has no pagination), E1 (wire `dimensions` through to runtime
validation), P1 (case-normalize reserved-keyword check via `snakecase`), E2 (two-tier
`VectorSearchResult[T]` + `SearchResults[T]` collection), X2 (`expression_names` escape hatch
+ aliased projections), E3 (Pydantic hydration of omitted embeddings via Optional vector
fields), P2 (required args before optional in generated signature), E4 (`top_k`/`dimensions`
bounds), E5 (EasySAM key-only attribute definitions), E6 (`types-boto3` floor)._

## Problem Statement

Prismarine should let a model declare a vector index and get a type-safe `search()` method
in the generated client, alongside the existing CRUD. Prismarine stores and searches
vectors via DynamoDB's native `SearchVectors` API (GA Aug 2026); it does **not** generate
embeddings — callers produce embeddings themselves (Bedrock Titan, Cohere, etc.) and pass
them in. The core must stay numpy-free, and clients for models without a vector index must
generate byte-identical output to today.

## Requirements

- New `@c.vector_index` decorator, stacked above `@c.model` like `@c.index`, accepting
  `index`, `attribute`, `dimensions`, `distance`, optional `hash`, optional `filters`.
- Each vector index generates a nested class (e.g. `ByEmbedding`) with a `search()` method
  using typed named kwargs (consistent with Prismarine's named-arg philosophy).
- HASH kwarg is **required** when the SearchSchema defines a HASH; inline-filter kwargs are
  **optional** (equality). Additionally provide an escape hatch (`condition_expression` /
  `expression_values` / `expression_names` passthrough) for advanced range/comparison
  filters the API supports on inline filters. `expression_names` lets callers alias
  DynamoDB reserved keywords used in the escape-hatch expression. (Decision 1-b; Critique X2)
- Results are deserialized via `boto3.dynamodb.types.TypeDeserializer` then run through the
  existing `prepare_item` (strip Decimals) to match CRUD output shape. (Decision 2-a)
- Because `search_vectors` is a **low-level client** call, all filter values and any
  escape-hatch `expression_values` must be wrapped into low-level `AttributeValue` maps
  (`{"S": ...}`, `{"N": ...}`) via `boto3.dynamodb.types.TypeSerializer`. Passing raw
  Python types triggers a boto3 `ParamValidationError`. (Critique E1)
- Auto-generated condition placeholders must be namespaced (e.g. `#pv_k_0` / `:pv_v_0`) so
  they cannot collide with user-supplied escape-hatch `expression_values`/`expression_names`.
  Projection attributes are likewise aliased to namespaced names (e.g. `#pv_proj_0`) so a
  projected DynamoDB reserved word does not raise `ValidationException`. (Critique E3, X2)
- `search()` returns a generic **collection** `SearchResults[T]` holding
  `hits: list[VectorSearchResult[T]]` and `consumed_capacity: dict[str, Any] | None`, and
  implementing `__iter__`/`__len__`/`__getitem__` (forwarding to `hits`). Each hit is a
  `VectorSearchResult[T]` with `item: T` and `score: float`. In pydantic mode each `item`
  is loaded via `_load_model`; in typed-dict mode it is the plain dict. (Decision 3-a;
  Critique X1, E2)
- **No pagination.** DynamoDB's native `SearchVectors` API has no `NextToken` and does not
  paginate; `TopK` is capped at 100. `search()` therefore exposes **no** `next_token`
  parameter. It accepts `return_consumed_capacity: str | None = None`, threaded through to
  the `SearchVectors` call (`ReturnConsumedCapacity`) and surfaced on the result as
  `consumed_capacity`. (Critique X1)
- DynamoDB omits the indexed embedding attribute from `SearchVectors` results by default
  (payload minimization), so a Pydantic model whose embedding field is required would raise
  `ValidationError` during hydration. Vector-attribute fields on models must therefore be
  **Optional** (e.g. `Embedding: list[float] | None = None`); callers who need the vector
  back must request it explicitly via `projection`. Document this. (Critique E3)
- Return the raw `Score` — do not re-sort or invert; score meaning depends on the distance
  function (COSINE/EUCLIDEAN: lower = closer; DOT_PRODUCT: higher = closer). Document it.
- Vector values are `numpy.ndarray`, gated behind `pip install prismarine[vectors]`. The
  vector helper duck-types the input (`.tolist()` when available, else `list(...)`) and
  formats it to the plain `[{"N": ...}]` shape (not `L`-wrapped). It performs pre-flight
  validation: assert every value is finite (`math.isfinite`, rejecting `NaN`/`Inf`) and,
  when `dimensions` is known, assert `len(vector) == dimensions` — failing fast locally
  rather than after a network round-trip. The generated `search()` always passes
  `dimensions` from the index metadata so this check is actually exercised at query time.
  numpy import stays lazy and confined to `runtime/dynamo_vectors.py`; the core never
  imports numpy. (Critique E2, E1-pass2)
- Enforce static bounds: `1 <= dimensions <= 4096` at decorator time and `1 <= top_k <= 100`
  at query time, raising a clear `ValueError` before any network call. (Critique E4)
- Add `get_client()` to the `DynamoAccess` base with a concrete default deriving from
  `self.get_resource().meta.client`, so existing custom-access classes inherit it
  unchanged. Document this for custom-access users. (Decision 4-a)
- Emit a `vectorindices` block into the EasySAM table dict, mirroring the existing
  `indices` style. (Decision 6-a)
- Pin conservative static floors on the `[vectors]` extra: `boto3 >= 1.43.89` (first boto3
  documenting `search_vectors`; service model shipped 2026-08-04) and a numpy floor. Bump
  the `types-boto3[dynamodb]` floor to `>= 1.43.89` so static type-checking sees
  `search_vectors` stubs. (Decision 5-c; Critique E6)
- Both `typed-dict` (default) and `pydantic` model libraries keep working.

## Background (codebase internals)

- **Generation**: `src/prismarine/prisma_client.py::build_client` walks `cluster.models`
  (sorted by `class_name`) and renders `src/prismarine/model.mako` once per model. The
  header imports CRUD helpers from `prismarine.runtime.dynamo_crud`. Pydantic vs typed-dict
  is selected via `model_library`; pydantic mode injects `PYDANTIC_HELPERS`.
- **Decorators**: `src/prismarine/runtime/cluster.py::Cluster` holds `model()`, `index()`,
  `export()`. `index()` finds the already-registered model dict and appends to
  `model['indexes']`. Vector indexes will follow the same pattern via a new
  `model['vector_indexes']` dict.
- **CRUD runtime**: `src/prismarine/runtime/dynamo_crud.py` operates on the resource/Table
  layer, which auto-(de)serializes. `prepare_item` strips `Decimal` to int/float. This is
  the function to reuse after low-level deserialization.
- **Access layer**: `src/prismarine/runtime/dynamo_access.py::DynamoAccess` (plain class
  with `...`-body stubs) exposes `get_resource()` and `get_table()`.
  `dynamo_default.py::DefaultDynamoAccess` implements them. `SearchVectors` is a low-level
  **client** call, so `get_client()` must be added.
- **EasySAM**: `src/prismarine/prisma_easysam.py::build_dynamo_tables` builds the table
  dict; `indices` is a list of dicts with `name` + `attributes`. `trigger`/`ttl` are added
  conditionally. `vectorindices` will follow the same conditional pattern.
- **Tests**: `tests/test_prisma_client_generation.py` renders clients into a temp dir and
  asserts on generated text; covers both model libraries.

### `SearchVectors` API shape (verified against boto3 docs)

- Params: `TableName`, `IndexName` (required), `SearchVector` (list of `{"N": ...}`,
  required), `TopK` (required, ≤ 100), `SearchConditionExpression` (string),
  `ExpressionAttributeNames`, `ExpressionAttributeValues`, `ProjectionExpression`,
  `ReturnConsumedCapacity`. There is **no** `NextToken`/pagination parameter.
- Filtering is via a **`SearchConditionExpression` string** (not a structured filter). HASH
  supports `=` only; inline filters support comparison/range. The helper builds
  `#pv_k_i = :pv_v_i` conjunctions from equality kwargs and appends any escape-hatch
  expression.
- Response: `{'SearchResults': [{'Item': <AttributeValue map>, 'Score': float}],
  'ConsumedCapacity': {...}}`. `Item` is low-level AttributeValue format → needs
  `TypeDeserializer` + `prepare_item`, and omits the embedding attribute unless explicitly
  projected. `ConsumedCapacity` is surfaced on `SearchResults`. No `NextToken` is returned.
- Score semantics: COSINE/EUCLIDEAN → k smallest (lower=closer); DOT_PRODUCT → k highest
  (higher=closer). Documented, not transformed.

## Constraints to respect

- Vector indexes require the table to be on-demand (`PAY_PER_REQUEST`).
- Up to 5 vector indexes per table; `1 <= dimensions <= 4096`.
- `SearchVectors` does **not** paginate (no `NextToken`); `1 <= TopK <= 100`.
- `SearchVector` payload is a plain list of `{"N": ...}`, not an `L` attribute.
- Both `typed-dict` (default) and `pydantic` model libraries must keep working.
- Models without a vector index must generate byte-identical output to today.
- boto3 must be new enough to have `search_vectors` (Aug 2026 service model).

## Architecture

```mermaid
flowchart LR
  M[models.py: @c.vector_index @ @c.model] --> C[Cluster.vector_index -> model['vector_indexes']]
  C --> G[build_client / model.mako]
  G --> GC[prismarine_client.py: ByEmbedding.search()]
  GC --> V[runtime/dynamo_vectors.py: _search_vectors]
  V --> A[DynamoAccess.get_client()]
  A --> DDB[(DynamoDB SearchVectors)]
  C --> E[prisma_easysam: vectorindices block]
```

## Proposed Solution

Add a `vector_index` decorator that records vector-index metadata on the model dict. Extend
`model.mako` to render a nested search class per vector index whose `search()` delegates to
a new central `runtime/dynamo_vectors.py` (`_search_vectors` + `SearchResults`), where all
numpy and low-level client logic lives lazily. Add `get_client()` to `DynamoAccess`. Emit a
`vectorindices` block in `prisma_easysam.py`. Gate numpy behind a `[vectors]` extra. Keep
generated files thin and non-vector output byte-identical.

### Declaration example

```python
@c.vector_index(
    index='by-embedding',
    attribute='Embedding',
    dimensions=1536,
    distance='COSINE',           # COSINE | EUCLIDEAN | DOT_PRODUCT
    hash='Category',             # optional SearchSchema HASH partition key
    filters=['Brand'],           # optional INLINE_FILTER attributes
)
@c.model(PK='ProductId')
class Product(TypedDict):
    ProductId: str
    Category: str
    Brand: str
    Embedding: list[float] | None  # Optional — SearchVectors omits it unless projected
```

### Generated method sketch

```python
class ProductModel(Model):
    ...
    class ByEmbedding:
        @staticmethod
        def search(
            *,
            vector,
            category: str,                # HASH — required, type from model schema
            top_k: int = 10,
            brand: str | None = None,     # inline filter — optional, type from model schema
            condition_expression: str | None = None,  # escape hatch
            expression_values: dict | None = None,
            expression_names: dict | None = None,
            projection: list[str] | None = None,
            return_consumed_capacity: str | None = None,
        ) -> SearchResults[Product]:
            ...
```

> Required args (`vector`, HASH) precede optional ones (`top_k`, filters, escape hatch) in
> the generated keyword-only signature for cleaner call-site ergonomics. (Critique P2)

## Task Breakdown

### Task 1: Add `vector_index` decorator + metadata to `Cluster`
- **Objective**: Extend `runtime/cluster.py` with a `VectorIndexConfig` TypedDict and a
  `vector_index(*, index, attribute, dimensions, distance, hash=None, filters=None)` method
  mirroring `index()`. Initialize `'vector_indexes': {}` in `model()`. Validate `distance`
  ∈ {COSINE, EUCLIDEAN, DOT_PRODUCT} and `1 <= dimensions <= 4096` (Critique E4). Validate
  that `hash` and every attribute in `filters`, **normalized via `snakecase()`**, avoid
  reserved generated-`search()` parameter names —
  `{'vector', 'top_k', 'condition_expression', 'expression_values', 'expression_names',
  'projection', 'return_consumed_capacity'}` — raising `ValueError` on collision so the
  generated staticmethod signature can never break. Normalizing first catches PascalCase
  fields (e.g. `Vector` → `vector`) that would otherwise pass registration and then emit a
  duplicate-argument `SyntaxError`. (Critique P1; note `next_token` is intentionally absent —
  there is no pagination.)
- **Tests**: Unit test that decorating a model registers vector-index metadata with correct
  fields; invalid `distance`/out-of-range `dimensions` raise; a `hash` or `filters` entry
  whose snakecased form matches a reserved name raises `ValueError` (include a PascalCase
  case such as `Vector`/`TopK`).
- **Demo**: Import a models module with `@c.vector_index`; show `model['vector_indexes']`
  populated.

### Task 2: Add `get_client()` to `DynamoAccess` with a default implementation
- **Objective**: In `runtime/dynamo_access.py` add `get_client(self)` returning
  `self.get_resource().meta.client`. `DefaultDynamoAccess` inherits it; custom-access
  classes (`myapp-custom-access`) inherit unchanged.
- **Tests**: Unit test with a stub subclass (mock resource with `.meta.client`) asserting
  `get_client()` returns the client, including a subclass that overrides only
  `get_resource`.
- **Demo**: `DefaultDynamoAccess().get_client()` returns a boto3 dynamodb client.

### Task 3: Create `runtime/dynamo_vectors.py` (`VectorSearchResult`, `SearchResults`, `_search_vectors`)
- **Objective**: New module defining a two-tier result model (Critique E2):
  `VectorSearchResult[T]` — a single hit with `item: T` and `score: float`; and
  `SearchResults[T]` — a collection with `hits: list[VectorSearchResult[T]]` and
  `consumed_capacity: dict[str, Any] | None = None`, implementing `__iter__`, `__len__`,
  and `__getitem__` forwarding to `hits`. Add `_format_vector(vector, dimensions=None)`
  that duck-types (`.tolist()` if present else `list(...)`) → `[{"N": str(x)}]` with
  pre-flight validation — assert every value is finite via `math.isfinite` (reject
  `NaN`/`Inf`) and, when `dimensions` is provided, assert `len(vector) == dimensions`,
  raising a clear `ValueError` before any network call (Critique E2). Add
  `_search_vectors(dynamo, table, index, *, vector, top_k, dimensions=None, hash_conditions,
  filter_conditions, condition_expression=None, expression_values=None,
  expression_names=None, projection=None, return_consumed_capacity=None)` that:
  - validates `1 <= top_k <= 100` locally (Critique E4) and formats the vector via
    `_format_vector(vector, dimensions=dimensions)` so dimension validation is actually
    exercised (Critique E1-pass2);
  - builds `SearchConditionExpression` from equality conditions using **namespaced
    placeholders** (`#pv_k_0 = :pv_v_0`, …, joined by `AND`) so they cannot collide with the
    escape-hatch expression (Critique E3), then appends the escape-hatch expression;
  - wraps every equality value and each `expression_values` entry into low-level
    `AttributeValue` maps via `boto3.dynamodb.types.TypeSerializer` (Critique E1);
  - assembles `ExpressionAttributeNames` by merging auto placeholders, caller-supplied
    `expression_names`, and **aliased projection names** (`#pv_proj_0`, … for each
    `projection` attribute) so projected DynamoDB reserved words cannot raise
    `ValidationException` (Critique X2); builds `ProjectionExpression` from those aliases;
  - threads `ReturnConsumedCapacity` when supplied (there is **no** `NextToken`);
  - calls `get_client().search_vectors(...)`, deserializes each result `Item` via
    `TypeDeserializer` + `prepare_item`, and returns `SearchResults(hits=[...],
    consumed_capacity=...)` (Critique X1). Lazy capability check raising a clear error if
    `search_vectors` is absent. numpy never imported by this module (duck-typing).
- **Tests**: `_format_vector` with numpy array (skipif absent) and plain list; pre-flight
  validation rejects `NaN`/`Inf` and a length mismatch against `dimensions` (Critique E2);
  `top_k` out of `[1, 100]` raises (Critique E4); a `_search_vectors` test with a fake
  `DynamoAccess` whose client returns a canned multi-hit payload (with `ConsumedCapacity`),
  asserting: deserialization, score passthrough, iteration over multiple
  `VectorSearchResult` hits with distinct scores + `len()`/indexing + `consumed_capacity`
  (Critique E2, X1), `TypeSerializer`-wrapped filter values (`{"S": ...}`/`{"N": ...}`)
  (Critique E1), namespaced condition-expression construction that does not clash with a
  supplied `expression_values`/`expression_names` (Critique E3), and aliased projection
  names (Critique X2). A numpy-absent import test asserting `'numpy' not in sys.modules`
  after importing core.
- **Demo**: Call `_search_vectors` against the fake access; print `SearchResults`.

### Task 4: Extend `model.mako` + `prisma_client.py` to render the vector search class
- **Objective**: Pass a sorted `VectorIndexes` list into the template render in
  `build_client` (`name`, `attribute`, `dimensions`, `distance`, `hash`, `filters`),
  including the model field type for the `hash` and each `filters` attribute resolved from
  the model schema so the template can annotate kwargs with real types instead of hardcoding
  `str` (Critique P2). In `model.mako`, after the GSI loop, render one nested class per
  vector index (PascalCase name) with a keyword-only `search(*, vector, <required HASH
  kwarg if hash>, top_k=10, <optional filter kwargs>, condition_expression=None,
  expression_values=None, expression_names=None, projection=None,
  return_consumed_capacity=None) -> SearchResults[Model]` where **required args precede
  optional ones** (Critique P2-pass2) and the HASH/filter kwargs carry their schema-derived
  type annotations (Critique P2-pass1). The generated body calls the imported
  `_search_vectors`, passing `dimensions=<index dimensions>` so pre-flight validation runs
  (Critique E1-pass2), `hash_conditions`/`filter_conditions` keyed by real attribute names,
  and `expression_names`/`return_consumed_capacity` (Critique X1, X2). Pydantic mode wraps
  each hit's item via `_load_model`; because `SearchVectors` omits the embedding attribute,
  models are expected to declare vector fields as Optional so hydration does not raise
  (Critique E3). Add `_search_vectors`, `SearchResults`, `VectorSearchResult` (and typing)
  to the header imports **only when at least one model has a vector index**, preserving
  byte-identical non-vector output.
- **Tests**: Extend `tests/test_prisma_client_generation.py` — assert emitted
  `class ByEmbedding:` + `def search(` with the required HASH kwarg appearing **before**
  `top_k` (Critique P2-pass2), optional filter kwargs carrying schema-derived type hints
  (e.g. a non-`str` filter field) (Critique P2-pass1), escape-hatch params including
  `expression_names` (Critique X2), **no** `next_token` param (Critique X1),
  `dimensions=` passed into the `_search_vectors` call (Critique E1-pass2),
  `SearchResults[Product]` return, conditional `_search_vectors`/`VectorSearchResult`
  import; a Pydantic-mode generation + hydration test where the response omits the embedding
  attribute and the Optional field loads cleanly (Critique E3); assert a no-vector model
  emits no vector imports (byte-identical guard). Cover both model libraries.
- **Demo**: Generate a client for a vector-index model; show `ByEmbedding.search`.

### Task 5: Emit the `vectorindices` EasySAM block
- **Objective**: In `prisma_easysam.py` iterate `data.get('vector_indexes', {})` and emit
  `result[short_name]['vectorindices']` as a list of dicts mirroring `indices`: `name`,
  `attribute`, `dimensions`, `distance`, plus `hash`/`filters` when present. Do **not**
  register vector `attribute`/`hash`/`filters` into the table's `attributes`
  (AttributeDefinitions) map: CloudFormation only permits attributes that serve as table or
  GSI/LSI key schema there, so adding arbitrary filter attributes would break deployment
  (Critique E5). Keep the vector metadata confined to the `vectorindices` block. When vector
  indexes exist, assert/enforce the table is `PAY_PER_REQUEST` (vector indexes require
  on-demand). Only add the `vectorindices` key when vector indexes exist.
- **Tests**: Unit test the emitted `vectorindices` shape; assert vector filter attributes
  are **absent** from the table `attributes`/AttributeDefinitions map (Critique E5); assert
  a non-`PAY_PER_REQUEST` table with vector indexes raises; test a model without vector
  indexes omits the key.
- **Demo**: `build_dynamo_tables` prints the emitted `vectorindices` block.

### Task 6: Wire the optional `[vectors]` extra, version floor, integration
- **Objective**: In `pyproject.toml` add `[project.optional-dependencies] vectors =
  ["numpy>=1.26", "boto3>=1.43.89"]` (keep core `boto3` as-is) and bump the
  `types-boto3[dynamodb]` floor to `>= 1.43.89` so static type-checking sees
  `search_vectors` stubs (Critique E6). Optionally re-export `SearchResults`/
  `VectorSearchResult`/`_search_vectors` guardedly without importing numpy at core import
  time. Run full test suite + `ruff format`/lint to confirm green and byte-identical
  non-vector output.
- **Tests**: Full `pytest`; numpy-absent guard confirms core stays numpy-free.
- **Demo**: `pip install -e .[vectors]` succeeds; suite passes; vector + non-vector client
  generation works.

### Task 7: Follow-ups — README, example model, docs
- **Objective**: Add a README `vector_index` section (declaration, search usage, escape
  hatch including `expression_names`, score semantics per distance function, **no-pagination
  + `TopK` ≤ 100** note, **Optional vector fields** caveat (`SearchVectors` omits the
  embedding unless projected), the `SearchResults`/`VectorSearchResult` collection shape,
  backfill `ValidationException` caveat + caller-retry note, `pip install
  prismarine[vectors]`, on-demand/5-indexes/1≤dims≤4096 constraints, "requires EasySAM ≥ X"
  note). Document `get_client()` for custom-access users. Add a vector-index model to
  `example/` (with an Optional embedding field) and regenerate its client.
- **Tests**: n/a (docs); regenerate example and confirm it renders.
- **Demo**: README renders the new section; `example/` has a working vector-index model +
  generated client.

## Out of Scope

- Generating embeddings (caller's job).
- Re-embedding stale content.
- Backfill/readiness handling (`SearchVectors` throws `ValidationException` while an index
  backfills and briefly after ACTIVE) — documented caveat only; callers must retry. No
  wait/retry helper.
- Changing existing GSI (`@c.index`) semantics.
- EasySAM CloudFormation support for `VectorIndexes` (coordinated separate change on the
  EasySAM side).
