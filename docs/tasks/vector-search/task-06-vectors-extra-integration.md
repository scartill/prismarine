---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: true
status: done
---

# Task 06: Wire the optional `[vectors]` extra, version floors, integration

- [x] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `task-03-dynamo-vectors-runtime.md`, `task-04-render-search-class.md`,
  `task-05-easysam-vectorindices.md`
- **Blocks**: `task-07-docs-example.md`
- **Parallelism**: `Run sequentially last among code tasks` (integration + full-suite gate)

## Objective
Declare the optional `vectors` dependency extra and bump version floors, keep core numpy-free,
and run the full test suite + ruff to confirm green and byte-identical non-vector output.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" — `[vectors]` extra with
  `boto3 >= 1.43.89` + numpy floor; `types-boto3[dynamodb] >= 1.43.89` floor (E6); core stays
  numpy-free.
- **Testing & risk strategy items**: Spec Task 6 tests (full `pytest`, numpy-absent guard);
  Critique E6 (pass-2).
- **Out of scope**: New feature behaviour (Tasks 1-5); docs/example (Task 7).

## Implementation Guidance
- **Files to create or modify**:
  - `pyproject.toml`:
    - Under `[project.optional-dependencies]` (currently only `pydantic = [...]`, ~lines
      16-19) add: `vectors = ["numpy>=1.26", "boto3>=1.43.89"]`.
    - Bump the base `types-boto3[dynamodb]` floor from `>=1.38.19` to `>=1.43.89` so static
      type-checking sees `search_vectors` stubs (E6). Leave the **core** `boto3>=1.38.19` as-is
      (the newer floor is scoped to the `[vectors]` extra); if the `search_vectors` capability
      check in Task 3 is the only runtime guard, document that non-vector users are unaffected.
  - `src/prismarine/runtime/__init__.py` (optional): guardedly re-export `SearchResults` /
    `VectorSearchResult` / `_search_vectors` **without** importing numpy at core import time
    (they live in `dynamo_vectors.py` which is already numpy-free, so a plain import is safe —
    confirm it does not transitively import numpy).
- **Data/API/UI behaviour**: Installing `prismarine[vectors]` pulls numpy + a new-enough boto3;
  a plain install never imports numpy.
- **Established patterns to follow**: The existing `pydantic` optional extra as the template for
  `vectors`.
- **Constraints and non-goals**: Do not add numpy to core deps. Do not change unrelated pins.

## Verification Requirements
- **Automated tests**:
  - Add/confirm a numpy-absent guard test: after importing the core package (not
    `dynamo_vectors` behaviour that duck-types numpy), assert `'numpy' not in sys.modules`.
    Prefer a subprocess check — **invoke via `uv run python`** (not bare `python`, which may
    not be on `PATH` in a uv-managed env; Critique E6, pass-2-tasks):
    `uv run python -c "import prismarine, sys; assert 'numpy' not in sys.modules"` — to avoid
    pollution from other tests that import numpy.
  - Run the **entire** suite: all pre-existing tests plus the new Task 1-5 tests must pass.
- **Manual / integration checks**:
  - `uv run pip install -e .[vectors]` (or `uv sync --extra vectors`) succeeds locally.
  - Generate both a vector-index client and a non-vector client; confirm the non-vector output
    is byte-identical to pre-feature output (diff against a saved baseline, e.g. regenerate the
    existing `example/myapp` client and `git diff` shows no change).
- **Risk coverage**: E6 (typing floor), core-numpy-free invariant, byte-identical guard.
- **Demo command**: `.venv\Scripts\python.exe -m pytest -q` with `.venv\Scripts` on `PATH`
  (so the generator's `ruff` subprocess resolves). `uv run pytest` also works **when** the
  environment can reach the package index; in an offline/locked environment `uv run` blocks on
  dependency resolution, so the venv-interpreter invocation is the reliable hermetic form.
  Lint/format: `ruff check src tests` (clean) and `ruff format --check .` (only pre-existing
  non-feature files differ).
- **Expected result**: Full suite green (48 passed, 1 skipped — the skip is the numpy-array
  `_format_vector` test, correct when numpy is absent); `ruff check` clean; numpy-absent guard
  holds; non-vector generated output byte-identical (example client regenerates with no diff).

## Handoff Notes
If `ruff format --check` flags generated-template whitespace, fix the `model.mako` text in
Task 4 rather than post-processing. Record the exact working test command here once confirmed
(the repo has no codified runner; `uv run pytest` is the expected invocation given
`[dependency-groups] dev`).
