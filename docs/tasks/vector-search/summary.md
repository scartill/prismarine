# Task Summary: DynamoDB Native Vector Search Support

- **Source spec**: `docs/specs/vector-search.md`
- **Task directory**: `docs/tasks/vector-search/`
- **Status**: `ready`

## Execution Order
1. `task-01-vector-index-decorator.md` — foundational metadata/decorator; other tasks read
   `model['vector_indexes']`.
2. `task-02-get-client.md` — access-layer `get_client()`; the runtime search depends on it.
3. `task-03-dynamo-vectors-runtime.md` — central runtime module (`_search_vectors`, result
   types); depends on Task 2's client handle.
4. `task-04-render-search-class.md` — template/generator rendering; depends on Task 1 (metadata
   shape) and Task 3 (runtime symbols).
5. `task-05-easysam-vectorindices.md` — EasySAM block; depends on Task 1 only (can run in
   parallel with Tasks 3-4).
6. `task-06-vectors-extra-integration.md` — pyproject extras/floors + full-suite gate; depends
   on Tasks 3-5.
7. `task-07-docs-example.md` — README + example client; depends on Tasks 4 and 6.

## Dependencies & Parallel Work
- **Sequential constraints**:
  - Task 3 after Task 2 (`_search_vectors` calls `get_client()`).
  - Task 4 after Tasks 1 **and** 3 (needs metadata shape + runtime symbols).
  - Task 6 after Tasks 3, 4, 5 (integration gate).
  - Task 7 after Tasks 4 and 6 (needs working generation + extras).
- **Safe parallel groups**:
  - Group A (independent, no shared files): Task 1 (`cluster.py`), Task 2 (`dynamo_access.py` /
    `dynamo_default.py`). Start together.
  - After Task 1: Task 5 (`prisma_easysam.py`) can run in parallel with Task 3
    (`dynamo_vectors.py`) and later Task 4.
- **Shared-file / integration warnings**:
  - Only Task 4 edits `prisma_client.py` and `model.mako` — no overlap with other tasks.
  - Only Task 1 edits `cluster.py` and `runtime/__init__.py`; Task 6 may also touch
    `runtime/__init__.py` for guarded re-exports — sequence Task 6 after Task 1 (it is already
    last) to avoid a merge on that file.
  - Tasks 1-5 each add their **own** new test file; Task 4 extends the existing
    `tests/test_prisma_client_generation.py` (sole editor of that file).

## Coverage Map
| Spec requirement / acceptance criterion | Risk or testing-strategy item | Task(s) | Verification evidence |
|---|---|---|---|
| `@c.vector_index` decorator + metadata | P1 (snakecase reserved check), E4 (dims bound) | 01 | `test_vector_index_decorator.py`: registration dict, invalid distance/dims raise, PascalCase collision raises |
| `get_client()` on `DynamoAccess` (Decision 4-a) | custom-access inheritance | 02 | `test_dynamo_access_get_client.py`: inherited client via `.meta.client` |
| `_search_vectors`, two-tier results | E1 (TypeSerializer), E2 (pre-flight + collection), E3 (namespaced), E4 (top_k), X1 (no NextToken), X2 (names/projection) | 03 | `test_dynamo_vectors.py`: request-shape + deserialization + bounds + guards |
| Generated nested `search()` class | P2 (ordering + type hints), X1, X2, E1-pass2 (dimensions), E3 (pydantic hydration), byte-identical non-vector | 04 | `test_prisma_client_generation.py`: substring asserts + byte-identical guard, both libraries |
| `vectorindices` EasySAM block (Decision 6-a) | E5 (no AttributeDefinitions pollution, on-demand) | 05 | `test_easysam_vectorindices.py`: block shape, attrs key-only, no-key-for-non-vector |
| `[vectors]` extra + version floors; core numpy-free | E6 (types-boto3 floor), numpy-absent guard | 06 | full `pytest`, numpy-absent subprocess check, install + byte-identical diff |
| README section, example model, custom-access docs | docs caveats (no pagination, Optional vector fields, retry) | 07 | regenerated example client renders; README section present |

## Shared Test and Demo Setup
- Runner: **pytest**, invoked as `uv run pytest -q` (the repo codifies no runner; `uv run
  pytest` matches `[dependency-groups] dev = [... pytest ...]`). Confirm and record the exact
  command during Task 6.
- Lint/format gate (generated output is ruff-formatted, single quotes, 120 cols):
  `ruff format --check .` and `ruff check src tests`.
- Generation tests use the existing `tests/test_prisma_client_generation.py` helpers
  (`_write_models`, `_stub_version`, `get_cluster`, `build_client`) — reuse them for new
  vector cases.
- numpy is optional: gate numpy-using assertions with `pytest.importorskip('numpy')`; run the
  numpy-absent guard in a subprocess to avoid cross-test import pollution.
- No AWS calls anywhere: Task 2/3 use fakes (`SimpleNamespace`, a fake client recording the
  request and returning a canned `SearchVectors` payload).

## Integration Checkpoint
After Tasks 1-5, run the full gate (Task 6):
1. `uv run pytest -q` — entire suite green (pre-existing + new).
2. `ruff format --check .` and `ruff check src tests` — clean.
3. Numpy-absent guard: `python -c "import prismarine, sys; assert 'numpy' not in sys.modules"`.
4. Regenerate `example/myapp` (non-vector) client and `git diff` — **no** change
   (byte-identical invariant).
5. Regenerate the new `example/` vector model (Task 7) client and confirm `ByEmbedding.search`
   renders.

## Open Questions
- **Billing-mode enforcement (Task 5 / E5):** the current model dict (`cluster.py` `model()`)
  does not carry a billing-mode field, and EasySAM `build_dynamo_tables` does not set one.
  Vector indexes require `PAY_PER_REQUEST`. Should the `@c.vector_index`/`@c.model` layer
  introduce/validate a billing-mode field, or is on-demand enforcement owned by the separate
  EasySAM CloudFormation change (spec Out of Scope)? Impact: whether Task 5 raises on
  non-on-demand tables or only documents the requirement. Owner: user / spec. Until resolved,
  Task 5 documents the requirement and asserts only where billing mode is actually known.
