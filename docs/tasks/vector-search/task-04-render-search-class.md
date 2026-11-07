---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: true
status: done
---

# Task 04: Render the vector search class in `model.mako` + `prisma_client.py`

- [x] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `task-01-vector-index-decorator.md`, `task-03-dynamo-vectors-runtime.md`
- **Blocks**: `None`
- **Parallelism**: `Run sequentially after task-01 and task-03` (needs the metadata shape and
  the runtime symbols); shares `prisma_client.py`/`model.mako` with no other task

## Objective
Generate, per vector index, a nested `search()` class in the client that delegates to
`_search_vectors`, with schema-derived kwarg types, required-before-optional ordering, the
`expression_names` escape hatch, `dimensions` passthrough, and Pydantic-safe hydration —
while keeping non-vector client output **byte-identical** to today.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" — generated nested `search()`,
  schema-derived filter type hints (P2-pass1), required-before-optional ordering (P2-pass2),
  `expression_names` (X2), `dimensions` wired to runtime (E1-pass2), no `next_token` (X1),
  Optional vector field hydration (E3), byte-identical non-vector output.
- **Testing & risk strategy items**: Spec Task 4 tests; Critique P2, X1, X2, E1, E3 (pass-2).
  Pass-2-tasks critique `docs/critiques/vector-search-tasks.md`: X1 (hashless index, 🎯), E1
  (import strictly from `dynamo_vectors` via `{vector_imports}` slot, 🎯), P1 (pydantic returns
  `SearchResults`, not a list, 🎯), E3 (`_pv_*` template locals, 🎯), E2 (no unused typing
  imports, 💡), E7 (defensive annotation stringification, 💡).
- **Out of scope**: The runtime search mechanics (Task 3), decorator (Task 1), EasySAM (Task 5).

## Implementation Guidance
- **Files to create or modify**:
  - `src/prismarine/prisma_client.py`:
    - In `build_client`'s per-model render call (the `model_template.render(...)` kwargs around
      lines 206-228), add a `VectorIndexes=[...]` kwarg built from `model['vector_indexes']`
      sorted by index name, each entry `{'name', 'attribute', 'dimensions', 'distance',
      'hash', 'hash_type', 'filters'}` where `filters` is a list of `{'attr', 'type'}`.
      Resolve `hash_type` and each filter `type` from the model's field annotations so the
      template can emit real type hints instead of `str` (P2-pass1). For TypedDict models read
      `model['cls'].__annotations__`; for pydantic read `model['cls'].model_fields[...]`
      annotations. **Render annotations defensively** (Critique E7, pass-2-tasks): under
      `from __future__ import annotations` the annotation may already be a `str`, so use
      `ann if isinstance(ann, str) else getattr(ann, '__name__', str(ann))`, defaulting to
      `'str'` when a type cannot be resolved — never crash generation and never emit invalid
      syntax.
    - Import the vector runtime symbols **only** from `prismarine.runtime.dynamo_vectors`
      (never from `dynamo_crud`, which does not define them — doing so causes a fatal
      `ImportError` in generated clients) (Critique E1, pass-2-tasks). Add a dedicated
      `{vector_imports}` slot to `HEADER_TEMPLATE` in `prisma_client.py` (or append an explicit
      header line) that, **only when at least one model in the cluster has a non-empty
      `vector_indexes`**, emits:
      `from prismarine.runtime.dynamo_vectors import _search_vectors, SearchResults, VectorSearchResult  # noqa`.
      When no model has a vector index the slot is the empty string, keeping non-vector output
      byte-identical. **Do not** add `Generic`/`TypeVar`/`Sequence` to `type_imports`: the
      generated `search()` only *uses* `SearchResults[Model]` (already imported) and unused
      names would trip Ruff `F401` (Critique E2, pass-2-tasks). Add a new typing name only if a
      generated construct actually references it.
  - `src/prismarine/model.mako`:
    - After the GSI `% endfor` (end of the `Indexes` loop, ~line 155), add
      `% for vindex in VectorIndexes:` rendering a nested `class ${pascal(vindex['name'])}:`
      with a single keyword-only staticmethod `search`:
      - Signature order (P2-pass2): `*, vector,` then the **required** HASH kwarg
        `${snake(vindex['hash'])}: ${vindex['hash_type']}` (**only when** `vindex['hash']` is
        set — a hashless index emits no HASH kwarg at all; Critique X1), then
        `top_k: int = 10,`, then each optional filter
        `${snake(f['attr'])}: ${f['type']} | None = None,`, then
        `condition_expression: str | None = None, expression_values: dict | None = None,
        expression_names: dict | None = None, projection: list[str] | None = None,
        return_consumed_capacity: str | None = None`. Return type
        `-> SearchResults[${Model}]`.
      - Body (use `_pv_`-prefixed locals so they can never shadow a user attribute kwarg —
        Critique E3, pass-2-tasks): initialise the HASH map safely for the **hashless** case
        (Critique X1, pass-2-tasks):
        `_pv_hash_conditions = {'${vindex['hash']}': ${snake(vindex['hash'])}} if vindex.get('hash') else {}`
        (render the literal dict only when `vindex['hash']` is set; otherwise emit
        `_pv_hash_conditions = {}`). Build `_pv_filter_conditions = {...}` from the provided
        (non-None) filter kwargs, keyed by the **real attribute names** (empty dict when none).
        Call:
        `_pv_results = _search_vectors(dynamo, ${ModelClass}.table_name, '${vindex['name']}',
        vector=vector, top_k=top_k, dimensions=${vindex['dimensions']},
        hash_conditions=_pv_hash_conditions, filter_conditions=_pv_filter_conditions,
        condition_expression=condition_expression, expression_values=expression_values,
        expression_names=expression_names, projection=projection,
        return_consumed_capacity=return_consumed_capacity)`.
      - `% if UsePydantic:` return a **`SearchResults`** (never a bare list — Critique P1,
        pass-2-tasks), preserving `consumed_capacity`:
        `return SearchResults(hits=[VectorSearchResult(item=_load_model(${Model}, _pv_hit.item),
        score=_pv_hit.score) for _pv_hit in _pv_results.hits],
        consumed_capacity=_pv_results.consumed_capacity)`.
        `% else:` `return _pv_results` as-is. Because `SearchVectors` omits the embedding
        attribute, pydantic hydration relies on the model declaring the vector field Optional
        (E3-pass2) — documented in Task 7; do not force-project here.
- **Established patterns to follow**: GSI nested-class loop in `model.mako:136-155`;
  `snake(...)`/`pascal(...)` template callables; `Indexes=[...]` construction in
  `prisma_client.py:214-224` as the model for `VectorIndexes=[...]`.
- **Constraints and non-goals**: Output goes through `ruff format` (single quotes, 120 cols) —
  write template text that formats cleanly. Non-vector models: zero new imports, zero new
  classes, byte-identical. Do not reorder or alter existing GSI/CRUD rendering.

## Verification Requirements
- **Automated tests**: Extend `tests/test_prisma_client_generation.py` (follow its existing
  `_write_models` + `get_cluster` + `build_client` + substring-assert pattern). Add:
  - A typed-dict model with `@cluster.vector_index(index='by-embedding', attribute='Embedding',
    dimensions=8, distance='COSINE', hash='Category', filters=['Rank'])` where `Rank: int`.
    Assert the generated `content` contains `class ByEmbedding:`, `def search(`, the HASH
    kwarg `category: str` appearing **before** `top_k` (P2-pass2), a filter kwarg
    `rank: int | None = None` carrying the real (non-`str`) type (P2-pass1), the
    `expression_names` param (X2), **no** `next_token` substring (X1),
    `dimensions=8` inside the `_search_vectors(` call (E1-pass2), and
    `-> SearchResults[<Model>]`. Assert the conditional import of `_search_vectors` /
    `VectorSearchResult` is present.
  - The same model in `model_library='pydantic'` (model inherits `BaseModel`, with
    `Embedding: list[float] | None = None`): assert the search body returns
    `SearchResults(hits=[VectorSearchResult(item=_load_model(...` — i.e. a `SearchResults`
    constructor preserving `consumed_capacity`, **not** a bare list (Critique P1) — and
    generation succeeds.
  - **Hashless index**: a model with `@cluster.vector_index(index='by-text',
    attribute='Embedding', dimensions=8, distance='COSINE')` (no `hash`, no `filters`).
    Assert the generated `search(` has **no** HASH kwarg, the body emits
    `_pv_hash_conditions = {}`, and the generated module imports/compiles without
    `UnboundLocalError`/`SyntaxError` (e.g. `compile(content, '<gen>', 'exec')` succeeds)
    (Critique X1).
  - **No-shadow guard**: generation for the normal model shows the search body uses
    `_pv_results` / `_pv_hash_conditions` / `_pv_filter_conditions` (not bare `results` etc.),
    confirming E3 locals are prefixed.
  - **Byte-identical guard**: a model with **no** vector index generates `content` with none of
    `_search_vectors`, `SearchResults`, `class ByEmbedding`, confirming non-vector output is
    unchanged (ideally compare against a snapshot of the pre-feature output for an identical
    model, or assert the vector-specific substrings are absent).
- **Manual / integration checks**: Generate a client for the `example/` vector model (Task 7)
  and eyeball `ByEmbedding.search`.
- **Risk coverage**: P2, X1, X2, E1-pass2, E3, and the byte-identical invariant.
- **Demo command**: `uv run pytest tests/test_prisma_client_generation.py -q`
- **Expected result**: New assertions pass; existing generation tests stay green.

## Handoff Notes
If the pydantic hydration-with-omitted-embedding test is hard to exercise without a live
response, cover it in Task 3's fake-client test plus a generation-text assertion here; the
end-to-end pydantic hydration is validated again in Task 6's full suite run.
