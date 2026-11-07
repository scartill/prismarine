---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: false
status: not-started
---

# Task 03: Create `runtime/dynamo_vectors.py` (result types + `_search_vectors`)

- [ ] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `task-02-get-client.md`
- **Blocks**: `task-04-render-search-class.md`
- **Parallelism**: `Safe with task-01` once Task 2 lands; shares no files with Task 4/5

## Objective
Create the central runtime module holding all low-level `SearchVectors` client logic and the
numpy-optional vector formatting, plus the two-tier result model. Generated clients import from
here; the core never imports numpy.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" — TypeSerializer wrapping (E1),
  namespaced placeholders (E3), two-tier `VectorSearchResult`/`SearchResults` (E2), no
  pagination / `consumed_capacity` only (X1), finite+dimension pre-flight validation (E2),
  `expression_names` + aliased projections (X2), `top_k` bounds (E4).
- **Testing & risk strategy items**: Spec Task 3 tests; Critique E1, E2, E3, E4, X1, X2 (pass-2).
  Pass-2-tasks critique `docs/critiques/vector-search-tasks.md`: X1 (optional `hash_conditions`
  + guarded iteration, 🎯), E4 (omit empty expression maps, 💡).
- **Out of scope**: Template rendering (Task 4), decorator validation (Task 1), EasySAM (Task 5).

## Implementation Guidance
- **Files to create or modify**:
  - `src/prismarine/runtime/dynamo_vectors.py` (new). Keep **numpy-free** (duck-typing only;
    numpy is never imported by this module). Contents:
    - `VectorSearchResult(Generic[T])`: a single hit with `item: T` and `score: float`
      (use `@dataclass(frozen=True)` or a simple class; `from typing import Generic, TypeVar`).
    - `SearchResults(Generic[T])`: collection with `hits: list[VectorSearchResult[T]]` and
      `consumed_capacity: dict[str, Any] | None = None`; implement `__iter__`, `__len__`,
      `__getitem__` forwarding to `hits` so `for r in results` / `len(results)` / `results[0]`
      work. **No** `next_token` field (X1).
    - `_format_vector(vector, dimensions=None)`: duck-type `vector.tolist()` if available else
      `list(vector)`; assert every element is finite via `math.isfinite(float(x))` raising a
      clear `ValueError` on `NaN`/`Inf`; when `dimensions` is not `None`, assert
      `len(values) == dimensions` else `ValueError`; return `[{"N": str(x)} for x in values]`
      (plain list of `{"N": ...}`, **not** `L`-wrapped). (E2)
    - `_search_vectors(dynamo, table, index, *, vector, top_k, dimensions=None,
      hash_conditions=None, filter_conditions=None, condition_expression=None,
      expression_values=None, expression_names=None, projection=None,
      return_consumed_capacity=None)` — `hash_conditions`/`filter_conditions` **default to
      `None`** (a hashless index passes no HASH), and every iteration over them must guard
      `(hash_conditions or {})` / `(filter_conditions or {})` so a `None` never raises
      (Critique X1, pass-2-tasks):
      1. Validate `1 <= top_k <= 100` → `ValueError` (E4).
      2. `search_vector = _format_vector(vector, dimensions=dimensions)` (E2/E1-pass2).
      3. Instantiate `TypeSerializer` and `TypeDeserializer` from `boto3.dynamodb.types`.
      4. Build equality conjunctions from `(hash_conditions or {})` then
         `(filter_conditions or {})` (dicts `{attr: value}`): for the i-th equality, use
         namespaced names `#pv_k_{i}` / `:pv_v_{i}` producing `#pv_k_{i} = :pv_v_{i}`; record
         `names['#pv_k_{i}'] = attr` and `values[':pv_v_{i}'] = serializer.serialize(value)`
         (E1, E3). Join with ` AND `.
      5. If `condition_expression` is provided, append it (wrap the auto part in parens and
         `AND` them, or append per spec); merge caller `expression_names` into `names` and
         serialize each `expression_values` entry via `TypeSerializer` into `values`
         (namespaced auto-keys cannot collide with caller keys) (E1, E3, X2).
      6. If `projection` is provided, alias each attribute to `#pv_proj_{i}` in `names` and
         build `ProjectionExpression = ', '.join('#pv_proj_{i}')` so a projected reserved word
         cannot raise `ValidationException` (X2).
      7. Assemble request: `TableName=table`, `IndexName=index`, `SearchVector=search_vector`,
         `TopK=top_k`, and conditionally `SearchConditionExpression`,
         `ExpressionAttributeNames`, `ExpressionAttributeValues`, `ProjectionExpression`,
         `ReturnConsumedCapacity`. **Only include `ExpressionAttributeNames` /
         `ExpressionAttributeValues` when their dict is non-empty** (`if names: request[...] =
         names`; `if values: request[...] = values`) — DynamoDB rejects empty expression maps
         with `ValidationException`, which happens e.g. when projecting with no conditions
         (Critique E4, pass-2-tasks). Likewise include `SearchConditionExpression` only when a
         condition string was actually built. **Never** pass `NextToken` (X1).
      8. `client = dynamo.get_client()`. Lazy capability check: if
         `not hasattr(client, 'search_vectors')`, raise a clear `RuntimeError` telling the user
         to upgrade boto3 (`>= 1.43.89`).
      9. `resp = client.search_vectors(**request)`. For each `{'Item', 'Score'}` in
         `resp.get('SearchResults', [])`: `item = prepare_item({k: deserializer.deserialize(v)
         for k, v in result['Item'].items()})`; append `VectorSearchResult(item=item,
         score=result['Score'])`.
      10. Return `SearchResults(hits=hits, consumed_capacity=resp.get('ConsumedCapacity'))`.
- **Data/API/UI behaviour**: `prepare_item` is reused from `dynamo_crud.py` to strip Decimals,
  matching CRUD output shape (Decision 2-a). Score is returned raw (no re-sort/invert).
- **Established patterns to follow**: `dynamo_crud.py` helper style (first arg `dynamo:
  DynamoAccess`, `prepare_item(...)` on results); import `prepare_item` from
  `prismarine.runtime.dynamo_crud`.
- **Constraints and non-goals**: Module must import cleanly with numpy absent; `math`,
  `typing`, `boto3.dynamodb.types` only. Do not import numpy anywhere. Keep pydantic-agnostic —
  hydration via `_load_model` happens in generated code (Task 4), not here; `item` here is the
  deserialized plain dict.

## Verification Requirements
- **Automated tests**: Add `tests/test_dynamo_vectors.py`. Cases:
  - `_format_vector([0.1, 0.2])` → `[{'N': '0.1'}, {'N': '0.2'}]`.
  - `_format_vector` with a numpy array (`pytest.importorskip('numpy')`) returns the same shape
    via `.tolist()`.
  - `_format_vector([float('nan')])` and `[float('inf')]` raise `ValueError`.
  - `_format_vector([0.1, 0.2], dimensions=3)` raises `ValueError`; `dimensions=2` passes.
  - `top_k=0` and `top_k=101` raise `ValueError`.
  - A fake `DynamoAccess` whose `get_client()` returns a fake client recording the request and
    returning a canned payload with two `SearchResults` (low-level `Item` AttributeValue maps +
    distinct `Score`s) and a `ConsumedCapacity`: assert deserialized items (Decimals stripped),
    scores preserved, iteration yields 2 `VectorSearchResult`, `len(results) == 2`,
    `results[0].score` correct, `results.consumed_capacity` set (E2, X1).
  - Assert the recorded request wraps filter values as `{'S': ...}` / `{'N': ...}` via
    TypeSerializer (E1), uses `#pv_k_0 = :pv_v_0`-style namespaced placeholders (E3), merges a
    supplied `expression_names`/`expression_values` without collision, aliases `projection`
    attributes to `#pv_proj_*` (X2), and contains **no** `NextToken` key (X1).
  - Capability check: a fake client lacking `search_vectors` raises `RuntimeError`.
  - **Hashless + no-filter call**: `_search_vectors(..., hash_conditions=None,
    filter_conditions=None, projection=['Title'])` does not raise, builds **no**
    `SearchConditionExpression`, omits `ExpressionAttributeValues` entirely (empty `values`),
    and still sends the `#pv_proj_*`-aliased `ProjectionExpression` with a non-empty
    `ExpressionAttributeNames` (Critique X1, E4).
  - **Empty-maps guard**: assert a request with neither conditions nor projection carries
    neither `ExpressionAttributeNames` nor `ExpressionAttributeValues` keys (Critique E4).
  - Import guard: `import prismarine.runtime.dynamo_vectors` then assert
    `'numpy' not in sys.modules` (when numpy not already imported by the test env; use a
    subprocess `python -c` check if the env pre-imports numpy).
- **Manual / integration checks**: Call `_search_vectors` against the fake access and print the
  `SearchResults`.
- **Risk coverage**: E1 (serialization), E2 (pre-flight), E3 (placeholder isolation), E4
  (bounds), X1 (no pagination), X2 (names/projection aliasing).
- **Demo command**: `uv run pytest tests/test_dynamo_vectors.py -q`
- **Expected result**: All cases pass; request assertions confirm wire-correct payload.

## Handoff Notes
Task 4 imports `_search_vectors`, `SearchResults`, `VectorSearchResult` from
`prismarine.runtime.dynamo_vectors` and passes `dimensions=<index dims>`,
`hash_conditions`/`filter_conditions` keyed by **real attribute names** (not snakecased), and
threads `expression_names`/`return_consumed_capacity`. Keep these symbol names stable.
