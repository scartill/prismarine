# Seed: DynamoDB Native Vector Search Support

## Intent

DynamoDB now has native vector search (GA Aug 2026): you can store vector embeddings on
your items and run similarity search via the `SearchVectors` API, no separate vector DB.
I want Prismarine to support this so a model can declare a vector index and get a
type-safe search method in the generated client, alongside the existing CRUD.

Prismarine stores and searches vectors — it does **not** generate embeddings. Callers
produce embeddings themselves (Bedrock Titan, Cohere, whatever) and pass them in.

## What I want

### Declaration — a new `@c.vector_index` decorator

A dedicated decorator, stacked above `@c.model` like `@c.index` is. Something like:

```python
@c.vector_index(
    index='by-embedding',
    attribute='Embedding',       # the item attribute holding the vector (L of N)
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

### Generated search method

Mirror the GSI nested-class pattern. Each vector index becomes a nested class with a
`search` method that uses typed named kwargs (consistent with Prismarine's named-arg
philosophy), returns a `SearchResults` type (item + score), and does **not** strip the
embedding attribute from results. Roughly:

```python
class ProductModel(Model):
    ...
    class ByEmbedding:
        @staticmethod
        def search(
            *,
            vector,                       # numpy array (or sequence)
            top_k: int = 10,
            category: str,                # HASH — required when schema defines one
            brand: str | None = None,     # inline filter — optional
            projection: list[str] | None = None,
        ) -> SearchResults[Product]:
            ...
```

- HASH kwarg is **required** when the SearchSchema defines a HASH; inline filters are
  optional kwargs. Equality-only for HASH (that's the API limit).
- Return the raw `Score`. Don't re-sort or invert — score meaning depends on the distance
  function (COSINE/EUCLIDEAN: lower = closer; DOT_PRODUCT: higher = closer). Document it.

### Vectors as numpy, behind an optional extra

Vector values should be `numpy.ndarray`. Gate numpy behind an optional dependency:
`pip install prismarine[vectors]`. The **core must stay numpy-free** — a normal install
and any non-vector generated client must never import numpy. The vector helper should
duck-type the input (`.tolist()` when available, else `list(...)`) and format it to the
plain `[{"N": ...}]` shape the `SearchVectors` API wants (note: not `L`-wrapped).

### Runtime client access

`SearchVectors` is a low-level boto3 **client** call, but Prismarine's `DynamoAccess`
only exposes the resource/`Table` layer today. Add `get_client()` to the `DynamoAccess`
ABC and to `DefaultDynamoAccess`. Give it a default implementation deriving from
`resource.meta.client` so existing custom-access classes (like
`example/myapp-custom-access`) keep working without changes.

### Where the code lives

Keep all numpy/vector logic in a single new runtime module (`runtime/dynamo_vectors.py`)
with a `_search_vectors(...)` helper and the `SearchResults` type. Generated clients just
import and call it — thin generated files, central logic, core CRUD untouched. The numpy
import stays lazy and confined to that one module.

### Infrastructure (EasySAM)

Emit a `vectorindices` block into the EasySAM table dict (from the model's vector-index
data), as if EasySAM already supports it. Actual EasySAM CloudFormation support for
`VectorIndexes` is a coordinated, separate change — we'll handle that on the EasySAM side.
Document it as "requires EasySAM ≥ X".

## Out of scope

- Generating embeddings (caller's job).
- Re-embedding stale content.
- Backfill/readiness handling: `SearchVectors` throws `ValidationException` while an index
  is backfilling and briefly after it goes ACTIVE. **Out of library scope** — just
  document the caveat and that callers must retry. No wait/retry helper.
- Changing existing GSI (`@c.index`) semantics.

## Constraints to respect

- Vector indexes require the table to be on-demand (`PAY_PER_REQUEST`).
- Up to 5 vector indexes per table; dimensions ≤ 4096.
- `SearchVector` payload is a plain list of `{"N": ...}`, not an `L` attribute.
- Both `typed-dict` (default) and `pydantic` model libraries must keep working.
- Models without a vector index must generate byte-identical output to today.
- boto3 must be new enough to have `search_vectors` (Aug 2026 service model) — verify /
  raise the minimum version.

## Follow-up tasks

- README: new `vector_index` section — declaration, search usage, score semantics per
  distance function, the backfill caveat, and `pip install prismarine[vectors]`.
- Add a vector-index model to `example/`.
- Extend `tests/test_prisma_client_generation.py` for the emitted search method and the
  `vectorindices` easysam block; add a runtime test for `_search_vectors` (numpy array
  and plain list); add a "numpy-absent" import test to prove the core stays numpy-free.

---

_Derived from `docs/brainstorms/VECTOR_SEARCH.md` (recommended Approach A)._
