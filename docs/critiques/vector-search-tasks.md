---
status: applied
target: docs/specs/vector-search.md docs/tasks/vector-search/
target-revision: 4994f1c61e711142b85c156d67d1977c2ef09a61
---

# Task-Level Critique: DynamoDB Native Vector Search Support

**Target Specification**: `docs/specs/vector-search.md`  
**Detailed Task Set**: `docs/tasks/vector-search/` (`summary.md`, `task-01` through `task-07`)  
**Target Revision**: `4994f1c61e711142b85c156d67d1977c2ef09a61`  
**Date**: 2026-11-07  
**Scope**: Autoflow Task-Level Pass (`--task-level`)  
**Verdict**: ⚠️ **PROCEED WITH UPDATES**

> **Status (applied 2026-11-07):** The 4 🎯 Must-Address findings (X1, E1, P1, E3) were
> auto-applied to the task files per Autoflow `--task-level --auto`. Additionally, the low-cost
> 💡 Recommendations E4, E5, E6, E7, and E8 were folded in. The 🤔 Question Q1 (billing-mode
> enforcement) is **left open** and recorded in `summary.md` Open Questions for human decision.
> The sections below are retained as the review record.

---

## Executive Summary

This task-level adversarial critique reviews the execution readiness of the detailed task set `docs/tasks/vector-search/` against the accepted Full Specification `docs/specs/vector-search.md`. Two prior specification-level critiques (`docs/critiques/vector-search.md` and `docs/critiques/vector-search-pass2.md`) resolved the core wire protocol, parameter normalisation, and collection architecture. The focus here is execution viability: implementation readiness, grounded paths and interfaces, verification completeness, and orchestration hazards.

The task breakdown is logically structured, preserves Prismarine's zero-numpy core guarantee, and provides granular per-task verification steps. However, this review identifies **4 Must-Address (🎯) items**, **5 Recommendations (💡)**, and **1 Question (🤔)** that would cause runtime crashes, syntax errors, or broken client imports during implementation:

1. **Undefined Variable and Runtime Type Failure on Hashless Vector Indexes (🎯 Must-Address)**: DynamoDB vector indexes do not mandate a partition key HASH. For a hashless index, `task-04` renders `hash_conditions` conditionally, leading to an immediate `UnboundLocalError`/`NameError` in the generated staticmethod, whilst `task-03` defines `hash_conditions` as a mandatory keyword-only argument without a default and iterates over it without a null check.
2. **Contradictory and Broken Client Import Instruction (🎯 Must-Address)**: `task-04` instructs adding runtime vector symbols (`_search_vectors`, `SearchResults`, `VectorSearchResult`) to the `dynamo_crud` import block, which does not define them, triggering fatal `ImportError` failures in generated clients.
3. **Ambiguous Collection Hydration Guidance in Pydantic Mode (🎯 Must-Address)**: `task-04` suggests constructing a "SearchResults/list of VectorSearchResult", inviting implementers to return a plain list and discard `consumed_capacity`, breaking the `SearchResults[T]` contract established in Pass-2.
4. **Duplicate Parameter Syntax Errors and Local Scope Shadowing in `search()` (🎯 Must-Address)**: `task-01` checks keywords against reserved names but fails to verify that filter attributes do not collide with the `hash` partition key or other filters. Furthermore, `task-04` introduces local variable assignments (`hash_conditions`, `filter_conditions`, `results`) that shadow user arguments.
5. **Empty Expression Maps Triggering DynamoDB `ValidationException` (💡 Recommendation)**: Omitting conditions whilst projecting attributes passes empty `ExpressionAttributeValues` maps to Boto3.
6. **Omission of Table-Level Vector Index Ceiling (≤ 5) (💡 Recommendation)**: Decorator-time validation enforces dimensions bounds but overlooks the DynamoDB table limit of 5 vector indexes.
7. **Unprefixed Subprocess Invocations in Test Guidance (💡 Recommendation)**: `python -c` verification commands in `task-06` fail on environments where Python is isolated within `uv`.
8. **Type Annotation Stringification Edge Cases (💡 Recommendation)**: Extraction of field annotations in `task-04` requires defensive handling for stringized annotations.
9. **Orchestration Parallelism Inconsistency (💡 Recommendation)**: `task-01` metadata falsely advertises concurrency with `task-03`, contradicting `summary.md`.
10. **Billing Mode Enforcement Verification Gap (🤔 Question)**: Ambiguity persists regarding whether Task 05 should assert on table billing mode in the absence of model schema support.

---

## Product Lens Review

### 1a. Implementation Readiness & Usability
- **Hashless Index Viability (Finding X1)**: While the specification allows optional `hash` on `@c.vector_index`, both `task-03` and `task-04` assume a partition key is always present. In `task-04-render-search-class.md` (lines 66-74), `hash_conditions` is declared only when `vindex['hash']` is truthy, yet it is referenced unconditionally in the `_search_vectors` invocation. When an index lacks a partition key, generated client calls fail immediately with an `UnboundLocalError`.
- **Collection Contract Integrity in Pydantic Mode (Finding P1)**: `task-04-render-search-class.md` (lines 75-77) states: `rewrap each hit's item via _load_model(${Model}, hit.item) (construct a new SearchResults/list of VectorSearchResult with loaded items), else return results as-is.` Returning a raw `list` rather than a `SearchResults[Model]` collection strips `consumed_capacity`, breaks iterable indexing abstractions, and violates the annotated return type `-> SearchResults[Model]`.

### 1b. Signature Ergonomics & Type Safety
- **Duplicate Argument Syntax Errors (Finding P2)**: `task-01-vector-index-decorator.md` validates that `hash` and `filters` attributes do not match the reserved parameter names. However, it fails to ensure that `snakecase(attr)` is distinct across the combination of `hash` and all elements of `filters`. If a model specifies `hash='Category', filters=['category']` or duplicate filters, Python raises `SyntaxError: duplicate argument 'category' in function definition` when loading the client.
- **Local Argument Shadowing (Finding E3)**: In `task-04-render-search-class.md`, the generated method executes:
  ```python
  results = _search_vectors(dynamo, ${ModelClass}.table_name, ...)
  return results
  ```
  If a model defines an attribute named `results`, `hash_conditions`, or `filter_conditions`, the local variable assignment overwrites the keyword argument, producing corrupted query requests or unexpected runtime behaviour.

### 1c. Verification & Demo Readiness
- **Absence of Hashless Vector Index Verification (Finding P3)**: Across all 7 task test specifications (`test_vector_index_decorator.py`, `test_dynamo_vectors.py`, `test_prisma_client_generation.py`, and `test_easysam_vectorindices.py`), every single test fixture supplies `hash='Category'`. There is zero test coverage for a vector index without a partition key, masking the `UnboundLocalError` in code generation.

---

## Engineering Lens Review

### 2a. Architecture & Interface Alignment
- **Contradictory Import Specifications (Finding E1)**: `task-04-render-search-class.md` (lines 46-50) instructs:
  > Add `_search_vectors`, `SearchResults`, `VectorSearchResult` to the `from prismarine.runtime.dynamo_crud import (...)` header block only when at least one model in the cluster has a non-empty `vector_indexes` (import them from `prismarine.runtime.dynamo_vectors`, a separate import line added conditionally).
  
  These symbols do not exist in `prismarine.runtime.dynamo_crud`. Placing them into the `dynamo_crud` import tuple causes an immediate `ImportError`. Moreover, `HEADER_TEMPLATE` in `src/prismarine/prisma_client.py` has fixed formatting slots and requires a dedicated `{vector_imports}` placeholder or an explicit append to the generated header text.

- **Unused Typing Imports (Finding E2)**: `task-04` directs adding `Generic`, `TypeVar`, and `Sequence` to client `type_imports` when vector indexes exist. The generated `ByEmbedding.search` signature utilizes only `SearchResults[Model]` (a parameterized generic instantiated from `dynamo_vectors`), and uses neither `Generic`, `TypeVar`, nor `Sequence`. Adding unused imports will trigger Ruff `F401` unused import errors unless explicitly avoided.

### 2b. Failure Modes & Wire Protocol Safety
- **Empty `ExpressionAttributeValues` Rejection (Finding E4)**: DynamoDB rejects requests where `ExpressionAttributeValues` or `ExpressionAttributeNames` is an empty dictionary (`ValidationException: ExpressionAttributeValues must not be empty`). In `task-03-dynamo-vectors-runtime.md`, when a search contains projections but no filter or hash conditions, `names` is populated with `#pv_proj_*` aliases while `values` remains `{}`. Assembling the request must ensure `ExpressionAttributeValues` is passed only when `bool(values)` is True.
- **Table Index Limit Enforcement (Finding E5)**: DynamoDB limits tables to a maximum of 5 vector indexes. While `task-01` validates `1 <= dimensions <= 4096`, it does not validate that `len(model['vector_indexes']) <= 5`. Declaring 6 indexes on a model passes client generation and only fails during remote infrastructure provisioning.

### 2c. Dependencies, Typing, & Runtime Environments
- **Subprocess Execution in `uv`-Managed Workspaces (Finding E6)**: `summary.md` (line 69) and `task-06-vectors-extra-integration.md` (line 54) mandate testing the numpy-absent invariant via `python -c "import prismarine, sys; assert 'numpy' not in sys.modules"`. On environments where Python is installed and managed via `uv`, the global executable `python` is not on `PATH`. The command must be codified as `uv run python -c "..."` (or `uv run --no-sync python -c "..."`).
- **Annotation Normalisation Defensiveness (Finding E7)**: `task-04` extracts schema types from `model['cls'].__annotations__` and `model_fields`. Under `from __future__ import annotations`, annotations are stored as raw strings rather than type objects. The guidance should instruct formatting annotations safely (e.g. `ann if isinstance(ann, str) else getattr(ann, '__name__', str(ann))`) to avoid invalid syntax in generated keyword annotations.

### 2d. Orchestration, Ordering, & File Ownership
- **Parallel Execution Metadata Discrepancy (Finding E8)**: `task-01-vector-index-decorator.md` (line 16) states: `Parallelism: Safe with task-02, task-03`. However, `summary.md` correctly indicates that `task-03` depends on `task-02`'s `get_client()` method. Declaring `task-03` safe to run concurrently with `task-01` before `task-02` lands creates a race hazard for automated dispatchers.

---

## Transversal Insights

1. **Hashless Index Robustness (Finding X1)**: A vector search design that requires a partition key eliminates one of the primary use cases of vector search: searching across an entire unpartitioned dataset. Correcting the contracts in `task-03` and `task-04` to handle `hash_conditions=None` simultaneously simplifies product ergonomics and prevents fatal runtime crashes.
2. **Collection Type Discipline (Finding P1 / E1)**: Ensuring `SearchResults[Model]` is preserved throughout Pydantic hydration reinforces type safety across the entire client API while safeguarding cost observability (`consumed_capacity`).

---

## Findings Summary Table

| ID | Lens | Severity | Category | Finding | Suggestion | Affected Documents |
|---|---|---|---|---|---|---|
| X1 | Transversal | 🎯 | Implementation Readiness | Hashless vector index generates invalid syntax (`UnboundLocalError`) in client and unhandled null iteration in `_search_vectors` | In `task-04`, initialise `hash_conditions = {'${vindex[\'hash\']}': ${snake(vindex[\'hash\'])}} if vindex.get(\'hash\') else {}`. In `task-03`, make `hash_conditions` default to `None` (`hash_conditions: dict | None = None`) and guard its iteration. Add a hashless test case to `task-01`, `task-03`, and `task-04`. | `task-03-dynamo-vectors-runtime.md`, `task-04-render-search-class.md` |
| E1 | Engineering | 🎯 | Architecture / Grounding | Contradictory import instruction directs importing vector symbols from `dynamo_crud`, causing `ImportError` in generated clients | Amend `task-04` to clarify that `_search_vectors`, `SearchResults`, and `VectorSearchResult` are imported exclusively from `prismarine.runtime.dynamo_vectors` via a dedicated `{vector_imports}` slot added to `HEADER_TEMPLATE`. | `task-04-render-search-class.md` |
| P1 | Product | 🎯 | Value / Contracts | Ambiguous guidance allows returning `list[VectorSearchResult]` in Pydantic mode, dropping `consumed_capacity` and violating return type hint | Amend `task-04` to explicitly require: `return SearchResults(hits=[VectorSearchResult(item=_load_model(${Model}, hit.item), score=hit.score) for hit in results.hits], consumed_capacity=results.consumed_capacity)`. | `task-04-render-search-class.md` |
| P2 | Product | 🎯 | Signature Ergonomics | Filter attributes matching the `hash` partition key or duplicate filters cause Python `SyntaxError: duplicate argument in function definition` | In `task-01`, add validation ensuring `filters` does not contain duplicate snakecased names and that no filter matches `snakecase(hash)`. | `task-01-vector-index-decorator.md`, `task-04-render-search-class.md` |
| E3 | Engineering | 🎯 | Failure Modes | Local variables `results`, `hash_conditions`, and `filter_conditions` in generated `search()` shadow user parameters with matching names | In `task-04`, use prefixed internal variable names (e.g. `_pv_results`, `_pv_hash_conditions`, `_pv_filter_conditions`), or add these names to the decorator-time reserved parameter set in `task-01`. | `task-01-vector-index-decorator.md`, `task-04-render-search-class.md` |
| E4 | Engineering | 💡 | Wire Protocol Safety | Assembling DynamoDB requests with empty `ExpressionAttributeValues={}` triggers `ValidationException` | In `task-03`, specify that `ExpressionAttributeValues` and `ExpressionAttributeNames` are conditionally included in the request payload only when their underlying dictionary is non-empty (`if values: request['ExpressionAttributeValues'] = values`). | `task-03-dynamo-vectors-runtime.md` |
| E5 | Engineering | 💡 | Operational Limits | Omission of DynamoDB table-level limit of 5 vector indexes at decorator time | In `task-01`, validate that `len(model['vector_indexes']) < 5` before registration, raising `ValueError` on the 6th index. | `task-01-vector-index-decorator.md` |
| E6 | Engineering | 💡 | Environment Grounding | Subprocess verification command `python -c` fails on systems without global Python in `PATH` | Amend `summary.md` and `task-06` demo commands to specify `uv run python -c "..."` (or `uv run --no-sync python -c "..."`). | `summary.md`, `task-06-vectors-extra-integration.md` |
| E7 | Engineering | 💡 | Implementation Readiness | Resolving annotations without considering stringized types can emit corrupted type hints | In `task-04`, specify extracting annotations with defensive string conversion (`ann if isinstance(ann, str) else getattr(ann, '__name__', str(ann))`, defaulting to `'str'`). | `task-04-render-search-class.md` |
| E8 | Engineering | 💡 | Orchestration | `task-01` metadata falsely advertises concurrency with `task-03`, contradicting the dependency graph | In `task-01`, update `Parallelism` to specify `Safe with task-02` only, removing `task-03`. | `task-01-vector-index-decorator.md` |
| Q1 | Product / Eng | 🤔 | Scope & Boundaries | Unresolved billing mode enforcement in `task-05` risks ambiguous tests or unilateral model schema alterations | Confirm whether `task-05` should enforce `PAY_PER_REQUEST` only when billing mode is explicitly present in metadata, leaving CloudFormation template enforcement to EasySAM. | `task-05-easysam-vectorindices.md`, `summary.md` |

---

## Verdict & Remediation Guidance

**Verdict**: ⚠️ **PROCEED WITH UPDATES**

The core architectural foundations, separation of concerns, and testing frameworks are sound. However, the task set must be updated to address the 4 Must-Address items prior to dispatching implementation workers:

1. **Update `task-03` and `task-04` for Hashless Indexes**: Make `hash_conditions` optional in `_search_vectors`, initialise it safely in `model.mako`, and add a dedicated test case for a hashless vector index.
2. **Clarify Import Pathways in `task-04`**: Provide clear instructions on adding a `{vector_imports}` slot to `HEADER_TEMPLATE` in `prisma_client.py` and importing strictly from `prismarine.runtime.dynamo_vectors`.
3. **Pin Pydantic Hydration Return Type in `task-04`**: Specify the exact `SearchResults(hits=[...], consumed_capacity=...)` constructor call in `model.mako`.
4. **Prevent Argument Collisions in `task-01` and `task-04`**: Check for overlap between `filters` and `hash` in `cluster.py`, and use private identifiers (`_pv_*`) for local template variables in `model.mako`.
