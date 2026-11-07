---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: false
status: not-started
---

# Task 07: Follow-ups — README, example model, docs

- [ ] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `task-04-render-search-class.md`, `task-06-vectors-extra-integration.md`
- **Blocks**: `None`
- **Parallelism**: `Run sequentially after the code tasks` (needs working generation)

## Objective
Document the feature and provide a working example: a README `vector_index` section and a
vector-index model added to `example/` with its regenerated client.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" + Task 7 — README section,
  `get_client()` docs for custom-access users, example model + regenerated client.
- **Testing & risk strategy items**: Spec Task 7 (docs: n/a tests; regenerate example and
  confirm it renders). Incorporate pass-2 doc notes: no-pagination/`TopK ≤ 100`, Optional
  vector fields, `expression_names`, the `SearchResults`/`VectorSearchResult` shape.
- **Out of scope**: Library code changes (Tasks 1-6).

## Implementation Guidance
- **Files to create or modify**:
  - `README.md`: add a `vector_index` section covering:
    - Declaration (`@c.vector_index(index=, attribute=, dimensions=, distance=, hash=,
      filters=)` stacked above `@c.model`), with the example model.
    - Search usage: the generated `ByEmbedding.search(*, vector, <hash>, top_k=..., <filters>,
      condition_expression=, expression_values=, expression_names=, projection=,
      return_consumed_capacity=)`, returning `SearchResults[T]` (a collection of
      `VectorSearchResult(item, score)` with `consumed_capacity`), iterable via
      `for hit in results`.
    - Escape hatch incl. `expression_names` for aliasing DynamoDB reserved keywords.
    - Score semantics per distance (COSINE/EUCLIDEAN: lower = closer; DOT_PRODUCT: higher =
      closer) — returned raw, not re-sorted.
    - **No pagination; `TopK` ≤ 100.**
    - **Optional vector fields**: `SearchVectors` omits the embedding unless `projection`
      requests it; models must declare the vector field Optional
      (`Embedding: list[float] | None`) to avoid pydantic hydration errors.
    - Backfill caveat: `SearchVectors` raises `ValidationException` while an index backfills and
      briefly after ACTIVE — callers must retry (no built-in wait/retry).
    - `pip install prismarine[vectors]`; constraints: on-demand table, ≤ 5 vector indexes per
      table, `1 <= dimensions <= 4096`; "requires EasySAM ≥ X" note for the infra side.
    - Document `get_client()` for custom-access users (inherited by default from
      `get_resource().meta.client`).
  - `example/`: add a vector-index model (e.g. extend `example/myapp/myobject/models.py` or add
    a new model) with `@c.vector_index` and an Optional embedding field, then regenerate its
    `prismarine_client.py` using the project's generate command (mirror how existing example
    clients were produced). Commit the regenerated client.
- **Established patterns to follow**: Existing README structure and the `example/myapp` /
  `example/myapp-custom-access` layout and generated `prismarine_client.py` files.
- **Constraints and non-goals**: Keep prose paraphrased and accurate; do not alter existing
  example models' behaviour beyond adding the vector index.

## Verification Requirements
- **Automated tests**: n/a (docs). 
- **Manual / integration checks**: Regenerate the example client and confirm it renders without
  error and contains the `ByEmbedding`-style search class; `git diff` on the example shows only
  the intended additions.
- **Risk coverage**: Documents the operational caveats (backfill retry, no pagination, Optional
  vector fields) so callers avoid runtime surprises.
- **Demo command**: regenerate the example client (project generate command, e.g.
  `uv run prismarine generate-client ...` per the CLI) and `uv run pytest -q`.
- **Expected result**: README renders the new section; `example/` has a working vector-index
  model + regenerated client; suite still green.

## Handoff Notes
This task is `Finalize`-adjacent but belongs to implementation because it ships an example
client. Any genuinely deferred doc items should be captured to `docs/feedback/` during
`Finalize`, not dropped here.
