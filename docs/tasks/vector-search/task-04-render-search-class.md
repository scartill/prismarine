---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: false
status: not-started
---

# Task 04: Render the vector search class in `model.mako` + `prisma_client.py`

- [ ] **Completion**
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
      annotations. Render the annotation to source text (reuse the existing approach the
      template uses for DTO lines, or `str`-fallback if resolution fails — never crash
      generation).
    - Add `_search_vectors`, `SearchResults`, `VectorSearchResult` to the
      `from prismarine.runtime.dynamo_crud import (...)` header block **only when at least one
      model in the cluster has a non-empty `vector_indexes`** (import them from
      `prismarine.runtime.dynamo_vectors`, a separate import line added conditionally). Add
      `Generic`/`TypeVar`/`Sequence` typing imports to both the pydantic and typed-dict
      `type_imports` branches (lines 243-249) **only when** a vector index exists. When no
      model has a vector index, emit nothing new — preserving byte-identical output (verify
      with the guard test below).
  - `src/prismarine/model.mako`:
    - After the GSI `% endfor` (end of the `Indexes` loop, ~line 155), add
      `% for vindex in VectorIndexes:` rendering a nested `class ${pascal(vindex['name'])}:`
      with a single keyword-only staticmethod `search`:
      - Signature order (P2-pass2): `*, vector,` then the **required** HASH kwarg
        `${snake(vindex['hash'])}: ${vindex['hash_type']}` (only when `vindex['hash']`), then
        `top_k: int = 10,`, then each optional filter
        `${snake(f['attr'])}: ${f['type']} | None = None,`, then
        `condition_expression: str | None = None, expression_values: dict | None = None,
        expression_names: dict | None = None, projection: list[str] | None = None,
        return_consumed_capacity: str | None = None`. Return type
        `-> SearchResults[${Model}]`.
      - Body: build `hash_conditions = {'${vindex['hash']}': ${snake(vindex['hash'])}}` (only
        when hash) and `filter_conditions = {...}` from the provided (non-None) filter kwargs,
        keyed by the **real attribute names**. Call
        `results = _search_vectors(dynamo, ${ModelClass}.table_name, '${vindex['name']}',
        vector=vector, top_k=top_k, dimensions=${vindex['dimensions']},
        hash_conditions=hash_conditions, filter_conditions=filter_conditions,
        condition_expression=condition_expression, expression_values=expression_values,
        expression_names=expression_names, projection=projection,
        return_consumed_capacity=return_consumed_capacity)`.
      - `% if UsePydantic:` rewrap each hit's `item` via `_load_model(${Model}, hit.item)`
        (construct a new `SearchResults`/list of `VectorSearchResult` with loaded items), else
        return `results` as-is. Because `SearchVectors` omits the embedding attribute, pydantic
        hydration relies on the model declaring the vector field Optional (E3) — documented in
        Task 7; do not force-project here.
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
    `Embedding: list[float] | None = None`): assert `_load_model` wrapping appears in the
    search body and generation succeeds.
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
