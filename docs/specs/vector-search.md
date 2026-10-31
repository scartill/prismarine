# Spec: DynamoDB Native Vector Search Support

_Derived from `docs/seed/vector-search.md`. Design decisions confirmed with the user
(numbered Q&A: 1-b, 2-a, 3-a, 4-a, 5-c, 6-a)._

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
  `expression_values` passthrough) for advanced range/comparison filters the API supports
  on inline filters. (Decision 1-b)
- Results are deserialized via `boto3.dynamodb.types.TypeDeserializer` then run through the
  existing `prepare_item` (strip Decimals) to match CRUD output shape. (Decision 2-a)
- `search()` returns a generic `SearchResults[T]` holding `item: T` and `score: float`.
  In pydantic mode `item` is loaded via `_load_model`; in typed-dict mode it is the plain
  dict. The embedding attribute is **not** stripped from results. (Decision 3-a)
- Return the raw `Score` — do not re-sort or invert; score meaning depends on the distance
  function (COSINE/EUCLIDEAN: lower = closer; DOT_PRODUCT: higher = closer). Document it.
- Vector values are `numpy.ndarray`, gated behind `pip install prismarine[vectors]`. The
  vector helper duck-types the input (`.tolist()` when available, else `list(...)`) and
  formats it to the plain `[{"N": ...}]` shape (not `L`-wrapped). numpy import stays lazy
  and confined to `runtime/dynamo_vectors.py`; the core never imports numpy.
- Add `get_client()` to the `DynamoAccess` base with a concrete default deriving from
  `self.get_resource().meta.client`, so existing custom-access classes inherit it
  unchanged. Document this for custom-access users. (Decision 4-a)
- Emit a `vectorindices` block into the EasySAM table dict, mirroring the existing
  `indices` style. (Decision 6-a)
- Pin conservative static floors on the `[vectors]` extra: `boto3 >= 1.43.89` (first boto3
  documenting `search_vectors`; service model shipped 2026-08-04) and a numpy floor.
  (Decision 5-c)
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
  required), `TopK` (required), `SearchConditionExpression` (string), `ExpressionAttributeNames`,
  `ExpressionAttributeValues`, `ProjectionExpression`, `ReturnConsumedCapacity`.
- Filtering is via a **`SearchConditionExpression` string** (not a structured filter). HASH
  supports `=` only; inline filters support comparison/range. The helper builds `#k = :k`
  conjunctions from equality kwargs and appends any escape-hatch expression.
- Response: `{'SearchResults': [{'Item': <AttributeValue map>, 'Score': float}],
  'ConsumedCapacity': {...}}`. `Item` is low-level AttributeValue format → needs
  `TypeDeserializer` + `prepare_item`.
- Score semantics: COSINE/EUCLIDEAN → k smallest (lower=closer); DOT_PRODUCT → k highest
  (higher=closer). Documented, not transformed.

## Constraints to respect

- Vector indexes require the table to be on-demand (`PAY_PER_REQUEST`).
- Up to 5 vector indexes per table; dimensions ≤ 4096.
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
    Embedding: list[float]
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
            top_k: int = 10,
            category: str,                # HASH — required
            brand: str | None = None,     # inline filter — optional
            condition_expression: str | None = None,  # escape hatch
            expression_values: dict | None = None,
            projection: list[str] | None = None,
        ) -> SearchResults[Product]:
            ...
```

## Task Breakdown

### Task 1: Add `vector_index` decorator + metadata to `Cluster`
- **Objective**: Extend `runtime/cluster.py` with a `VectorIndexConfig` TypedDict and a
  `vector_index(*, index, attribute, dimensions, distance, hash=None, filters=None)` method
  mirroring `index()`. Initialize `'vector_indexes': {}` in `model()`. Validate `distance`
  ∈ {COSINE, EUCLIDEAN, DOT_PRODUCT} and `dimensions` ≤ 4096.
- **Tests**: Unit test that decorating a model registers vector-index metadata with correct
  fields; invalid `distance`/`dimensions` raise.
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

### Task 3: Create `runtime/dynamo_vectors.py` (`SearchResults`, `_search_vectors`)
- **Objective**: New module with a generic `SearchResults`/`VectorSearchResult` type
  (`item: T`, `score: float`); `_format_vector(vector)` that duck-types (`.tolist()` if
  present else `list(...)`) → `[{"N": str(x)}]`; and `_search_vectors(dynamo, table, index,
  *, vector, top_k, hash_conditions, filter_conditions, condition_expression=None,
  expression_values=None, projection=None)` that builds `SearchConditionExpression` from
  equality conditions (`#k = :k` joined by `AND`), appends the escape-hatch expression,
  assembles names/values, calls `get_client().search_vectors(...)`, deserializes each
  result `Item` via `TypeDeserializer` + `prepare_item`, returns `SearchResults`. Lazy
  capability check raising a clear error if `search_vectors` is absent. numpy never imported
  by this module (duck-typing).
- **Tests**: `_format_vector` with numpy array (skipif absent) and plain list; a
  `_search_vectors` test with a fake `DynamoAccess` whose client returns a canned payload,
  asserting deserialization + score passthrough + condition-expression construction. A
  numpy-absent import test asserting `'numpy' not in sys.modules` after importing core.
- **Demo**: Call `_search_vectors` against the fake access; print `SearchResults`.

### Task 4: Extend `model.mako` + `prisma_client.py` to render the vector search class
- **Objective**: Pass a sorted `VectorIndexes` list into the template render in
  `build_client` (`name`, `attribute`, `distance`, `hash`, `filters`). In `model.mako`,
  after the GSI loop, render one nested class per vector index (PascalCase name) with a
  `search(*, vector, top_k=10, <hash kwarg if hash>, <optional filter kwargs>,
  condition_expression=None, expression_values=None, projection=None) -> SearchResults[Model]`
  that calls the imported `_search_vectors`, passing `hash_conditions`/`filter_conditions`
  keyed by real attribute names. Pydantic mode wraps items via `_load_model`. Add
  `_search_vectors`, `SearchResults` (and typing) to the header imports **only when at least
  one model has a vector index**, preserving byte-identical non-vector output.
- **Tests**: Extend `tests/test_prisma_client_generation.py` — assert emitted
  `class ByEmbedding:` + `def search(` with required HASH kwarg, optional filter kwargs,
  escape-hatch params, `SearchResults[Product]` return, conditional `_search_vectors`
  import; assert a no-vector model emits no vector imports (byte-identical guard). Cover
  both model libraries.
- **Demo**: Generate a client for a vector-index model; show `ByEmbedding.search`.

### Task 5: Emit the `vectorindices` EasySAM block
- **Objective**: In `prisma_easysam.py` iterate `data.get('vector_indexes', {})` and emit
  `result[short_name]['vectorindices']` as a list of dicts mirroring `indices`: `name`,
  `attribute`, `dimensions`, `distance`, plus `hash`/`filters` when present. Register
  `hash`/`filters` attributes in the `attributes` map following the existing index pattern.
  Only add the key when vector indexes exist.
- **Tests**: Unit test the emitted `vectorindices` shape; test a model without vector
  indexes omits the key.
- **Demo**: `build_dynamo_tables` prints the emitted `vectorindices` block.

### Task 6: Wire the optional `[vectors]` extra, version floor, integration
- **Objective**: In `pyproject.toml` add `[project.optional-dependencies] vectors =
  ["numpy>=1.26", "boto3>=1.43.89"]` (keep core `boto3` as-is). Optionally re-export
  `SearchResults`/`_search_vectors` guardedly without importing numpy at core import time.
  Run full test suite + `ruff format`/lint to confirm green and byte-identical non-vector
  output.
- **Tests**: Full `pytest`; numpy-absent guard confirms core stays numpy-free.
- **Demo**: `pip install -e .[vectors]` succeeds; suite passes; vector + non-vector client
  generation works.

### Task 7: Follow-ups — README, example model, docs
- **Objective**: Add a README `vector_index` section (declaration, search usage, escape
  hatch, score semantics per distance function, backfill `ValidationException` caveat +
  caller-retry note, `pip install prismarine[vectors]`, on-demand/5-indexes/≤4096-dims
  constraints, "requires EasySAM ≥ X" note). Document `get_client()` for custom-access
  users. Add a vector-index model to `example/` and regenerate its client.
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
