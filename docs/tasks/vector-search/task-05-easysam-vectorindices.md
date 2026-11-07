---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: false
status: not-started
---

# Task 05: Emit the `vectorindices` EasySAM block

- [ ] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `task-01-vector-index-decorator.md`
- **Blocks**: `None`
- **Parallelism**: `Safe with task-04` (different file: `prisma_easysam.py`)

## Objective
Emit a `vectorindices` block into the EasySAM table dict from the model's vector-index
metadata, mirroring the existing `indices` conditional pattern — **without** polluting
CloudFormation `AttributeDefinitions` with non-key attributes, and enforcing on-demand billing.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" — "Emit a `vectorindices` block
  into the EasySAM table dict, mirroring the existing `indices` style" (Decision 6-a).
- **Testing & risk strategy items**: Spec Task 5 tests; Critique E5 (pass-2): do not register
  non-key vector attributes into `attributes`; enforce `PAY_PER_REQUEST`.
- **Out of scope**: Actual CloudFormation template generation for `VectorIndexes` (coordinated
  separate EasySAM-side change, per spec "Out of Scope"). This task only emits the dict block.

## Implementation Guidance
- **Files to create or modify**:
  - `src/prismarine/prisma_easysam.py` in `build_dynamo_tables` (per-model loop, after the GSI
    `indices` build and before/alongside the `trigger`/`ttl` conditionals, ~lines 24-68):
    - Iterate `data.get('vector_indexes', {})`. For each `(name, vindex)` build a dict
      `{'name': name, 'attribute': vindex['attribute'], 'dimensions': vindex['dimensions'],
      'distance': vindex['distance']}`, adding `'hash': vindex['hash']` when truthy and
      `'filters': vindex['filters']` when non-empty. Collect into a `vector_indices` list.
    - **Do NOT** add `attribute`/`hash`/`filters` into the `attributes` (AttributeDefinitions)
      map (Critique E5): CloudFormation only permits key-schema attributes there, so arbitrary
      filter attributes would break deployment. Keep all vector metadata inside the
      `vectorindices` block only.
    - Emit conditionally: `if vector_indices: result[short_name]['vectorindices'] =
      vector_indices` — matching the existing `if indices:` / `if 'trigger' in data:` pattern
      (lines 59-68).
    - When a model has vector indexes, enforce on-demand billing: if the model/table declares a
      billing mode that is not `PAY_PER_REQUEST`, raise `UserWarning`/`ValueError` with a clear
      message (vector indexes require on-demand). If billing mode is not represented in the
      current model dict, document the assumption in a code comment and assert at whatever layer
      billing is known; do not silently emit an invalid combination. Record any ambiguity in
      Open Questions below rather than inventing a billing field.
- **Established patterns to follow**: The `indices` build + `if indices:` emit at
  `prisma_easysam.py:24-60`; `trigger`/`ttl` conditionals at lines 63-68; the
  `named_dict_to_item` helper for `attributes` (do not extend it with vector attrs).
- **Constraints and non-goals**: Models without vector indexes must omit the `vectorindices`
  key entirely (no empty list). No change to `attributes`, `indices`, `trigger`, or `ttl`
  emission for existing models.

## Verification Requirements
- **Automated tests**: Add `tests/test_easysam_vectorindices.py`. Build a `Cluster` with a
  model carrying a vector index (use the Task 1 decorator), call
  `build_dynamo_tables(prefix, cluster)`, and assert:
  - `result[short_name]['vectorindices']` is a list with the expected `name`, `attribute`,
    `dimensions`, `distance`, and `hash`/`filters` when present.
  - The vector `attribute`, `hash`, and `filters` names are **absent** from
    `result[short_name]['attributes']` (the AttributeDefinitions list) unless they are
    independently the table/GSI key (E5).
  - A model with **no** vector index produces a `result[short_name]` dict with **no**
    `vectorindices` key.
  - (If billing mode is modeled) a vector-index model declared non-`PAY_PER_REQUEST` raises.
- **Manual / integration checks**: `build_dynamo_tables` prints the emitted `vectorindices`
  block for the `example/` vector model.
- **Risk coverage**: E5 (CloudFormation AttributeDefinitions pollution + on-demand enforcement).
- **Demo command**: `uv run pytest tests/test_easysam_vectorindices.py -q`
- **Expected result**: `vectorindices` emitted correctly; `attributes` stays key-only; no key
  for non-vector models.

## Handoff Notes
The downstream EasySAM CloudFormation support for `VectorIndexes` is a separate coordinated
change (spec Out of Scope). This task's output is the dict contract that change will consume.
If billing mode is not currently represented on the model dict, flag it as an Open Question for
the user rather than adding a new model field unilaterally.
