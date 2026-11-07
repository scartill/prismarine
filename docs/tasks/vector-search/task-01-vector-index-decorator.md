---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: true
status: done
---

# Task 01: Add `vector_index` decorator + metadata to `Cluster`

- [x] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `None`
- **Blocks**: `task-04-render-search-class.md`, `task-05-easysam-vectorindices.md`
- **Parallelism**: `Safe with task-02` (distinct files; `task-03` depends on `task-02`, so it
  is not a safe concurrent peer of task-01 before task-02 lands — Critique E8)

## Objective
Extend `src/prismarine/runtime/cluster.py` with a `VectorIndexConfig` TypedDict and a
`vector_index()` decorator that records vector-index metadata onto the model dict under a new
`'vector_indexes'` key, mirroring the existing `index()` decorator. Perform all decorator-time
validation here so the generated client can never produce an invalid signature.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" bullets 1 (`@c.vector_index`
  decorator), the `snakecase` reserved-keyword rule, and the `1 <= dimensions <= 4096` bound.
- **Testing & risk strategy items**: Spec Task 1 tests; Critique P1 (case-normalized reserved
  keyword check), Critique E4 (`dimensions` bounds). Pass-2 critique
  `docs/critiques/vector-search-pass2.md` findings P1, E4. Pass-2-tasks critique
  `docs/critiques/vector-search-tasks.md`: P2 (duplicate/hash-collision names, 🎯), E3
  (internal-local names in reserved set, 🎯), E5 (≤ 5 index ceiling, 💡), E8 (parallelism, 💡),
  X1 (hashless index registers cleanly, 🎯).
- **Out of scope**: Code generation, runtime search, EasySAM emission (later tasks). The
  `top_k` bound (`1 <= top_k <= 100`) belongs to Task 3 (query time), not here.

## Implementation Guidance
- **Files to create or modify**:
  - `src/prismarine/runtime/cluster.py`: add `VectorIndexConfig(TypedDict)` alongside
    `TriggerConfig` (top of file, lines 1-10 region), with keys:
    `index: str`, `attribute: str`, `dimensions: int`, `distance: Literal['COSINE',
    'EUCLIDEAN', 'DOT_PRODUCT']`, `hash: NotRequired[str]`, `filters: NotRequired[list[str]]`.
    In `Cluster.model()`'s inner `decorator(cls)` (the `model_data = {...}` literal, lines
    34-41), add `'vector_indexes': {}` so every model has the key initialized. Add a
    `vector_index()` method mirroring `index()` (lines 57-69): keyword-only
    `def vector_index(self, *, index: str, attribute: str, dimensions: int, distance: str,
    hash: str | None = None, filters: list[str] | None = None)` returning an inner
    `decorator(cls)` that finds the model via `next((m for m in self.models if m['cls'] == cls),
    None)`, raising the same "must be placed above model decorator" `Exception` if absent, then
    sets `model['vector_indexes'][index] = {'attribute': attribute, 'dimensions': dimensions,
    'distance': distance, 'hash': hash, 'filters': filters or []}` and returns `cls`.
  - `src/prismarine/runtime/__init__.py`: add `VectorIndexConfig` to the
    `from prismarine.runtime.cluster import ...` re-export line (next to `Cluster, TriggerConfig`).
- **Data/API/UI behaviour**:
  - Validate `distance` ∈ `{'COSINE', 'EUCLIDEAN', 'DOT_PRODUCT'}` → `ValueError` otherwise.
  - Validate `1 <= dimensions <= 4096` → `ValueError` otherwise (Critique E4, pass-2).
  - Build the reserved set — note it now includes the generated method's **internal local
    variable names** so a model attribute can never shadow them (Critique E3, pass-2-tasks):
    `{'vector', 'top_k', 'condition_expression', 'expression_values', 'expression_names',
    'projection', 'return_consumed_capacity', 'results', 'hash_conditions',
    'filter_conditions'}` (note: **no** `next_token` — there is no pagination). Normalize
    `hash` and each `filters` attribute via `snakecase(attr)` before membership-testing; raise
    `ValueError` naming the offending attribute on collision (Critique P1). This catches
    PascalCase fields like `Vector`/`TopK` that would otherwise emit a duplicate-argument
    `SyntaxError` in the generated client. (Task 4 additionally prefixes its template locals
    `_pv_*` as defence-in-depth, but this reserved-set check is the authoritative guard.)
  - **Reject duplicate / collapsing snakecased names** (Critique P2, pass-2-tasks): collect the
    snakecased forms of `hash` (when set) and every `filters` entry; if any two collapse to the
    same name — e.g. `hash='Category', filters=['category']`, or `filters=['Brand', 'brand']` —
    raise `ValueError`, because the generated `search()` would otherwise have duplicate
    parameters (`SyntaxError: duplicate argument`).
  - **Enforce the table vector-index ceiling** (Critique E5, pass-2-tasks, 💡 applied here as it
    is one line and prevents a late infra failure): after registering, if
    `len(model['vector_indexes']) > 5` raise `ValueError` — DynamoDB permits at most 5 vector
    indexes per table.
- **Established patterns to follow**: `Cluster.index()` at `cluster.py:57-69` for structure;
  `from caseconverter import snakecase` (same package used in `prisma_client.py:9`) for
  normalization — do not add a bespoke casing helper.
- **Constraints and non-goals**: Keep `vector_index()` decorator-time only; no boto3/numpy
  imports in `cluster.py`. Models without a `@c.vector_index` keep `'vector_indexes': {}` and
  must remain byte-identical downstream.

## Verification Requirements
- **Automated tests**: Add `tests/test_vector_index_decorator.py` (new file). Cases:
  - Decorating a model with `@cluster.vector_index(index='by-embedding', attribute='Embedding',
    dimensions=1536, distance='COSINE', hash='Category', filters=['Brand'])` registers
    `model['vector_indexes']['by-embedding']` with the exact expected dict.
  - A model with no vector index still has `'vector_indexes': {}`.
  - Invalid `distance='MANHATTAN'` raises `ValueError`.
  - `dimensions=0` and `dimensions=5000` each raise `ValueError`.
  - A reserved HASH `hash='Vector'` (PascalCase → `snakecase` → `vector`) raises `ValueError`;
    likewise `filters=['TopK']`. A non-colliding `hash='Category'` does not raise.
  - A HASH/filter collision `hash='Category', filters=['category']` raises `ValueError`, and
    duplicate filters `filters=['Brand', 'brand']` raise `ValueError` (Critique P2).
  - An attribute named like an internal local — `hash='Results'` or `filters=['hash_conditions']`
    — raises `ValueError` (Critique E3 reserved-set).
  - Registering a 6th vector index on one model raises `ValueError` (Critique E5, ≤ 5 ceiling).
  - A **hashless** vector index (`@cluster.vector_index(index='by-embedding',
    attribute='Embedding', dimensions=8, distance='COSINE')` — no `hash`, no `filters`)
    registers with `hash=None` and `filters=[]` and does **not** raise (Critique X1 coverage).
  - `vector_index` applied with no `@cluster.model` beneath raises the "must be placed above
    model decorator" `Exception`.
  - Build the `Cluster` inline in-test (mirror how `cluster.py` is exercised) — no temp-dir
    client render needed for this task.
- **Manual / integration checks**: Import `example/myapp` style module with a vector index and
  inspect `cluster.models[0]['vector_indexes']`.
- **Risk coverage**: Verifies P1 (case collision) and E4 (dimension bounds) at the earliest
  gate, before any generation.
- **Demo command**: `uv run pytest tests/test_vector_index_decorator.py -q`
- **Expected result**: All new cases pass; registration dict matches; each invalid input
  raises the expected exception.

## Handoff Notes
Task 4 (render) and Task 5 (EasySAM) both read `model['vector_indexes']` — keep the dict shape
exactly `{'attribute', 'dimensions', 'distance', 'hash', 'filters'}` with `hash` possibly
`None` and `filters` always a list (possibly empty). The index name is the dict key.
