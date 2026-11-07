# Deferred Items — vector-search

**Date**: 2026-11-07
**Source spec**: docs/specs/vector-search.md
**Mode**: autoflow

## Summary
Native DynamoDB vector search shipped: a `@c.vector_index` decorator, a generated type-safe
`ByEmbedding.search()` method returning a `SearchResults[T]` collection, a numpy-free runtime
(`dynamo_vectors.py`), `get_client()` on the access layer, an EasySAM `vectorindices` block,
and the optional `[vectors]` extra. Three critique passes and one code-review pass were applied.
A few consciously-deferred items remain.

## Deferred Items

| ID | Origin | Priority | Item | Rationale / Next Step |
|----|--------|----------|------|-----------------------|
| D1 | Critique 🤔 (vector-search-tasks.md Q1) | Medium | Billing-mode (`PAY_PER_REQUEST`) enforcement for vector-index tables | The model dict carries no billing-mode field, so Task 5 documents the on-demand requirement and defers hard enforcement to the EasySAM CloudFormation side. Decide whether `@c.model`/`@c.vector_index` should introduce/validate a billing-mode field, or leave enforcement entirely to EasySAM. |
| D2 | Code Review LOW (review §LOW) | Low | `build_client` strips decorators with a single-line regex (`@.+?\n`); a **multi-line** `@c.vector_index(...)` on a TypedDict model leaks continuation lines into the generated `UpdateDTO` | Pre-existing generator limitation, not introduced here. Workaround: keep the decorator on one line. Follow-up: make the decorator-strip handle multi-line/balanced-paren decorators. |
| D3 | Spec Out-of-Scope | Medium | EasySAM CloudFormation support for `VectorIndexes` | Prismarine emits the `vectorindices` dict block; the actual CloudFormation resource generation is a coordinated, separate change on the EasySAM side ("requires EasySAM ≥ X"). |
| D4 | Implementation / environment | Low | `uv.lock` not regenerated for the new `[vectors]` extra + bumped `types-boto3`/`boto3` floors | `uv sync`/`uv lock` hung on dependency resolution in this (offline/locked) environment; a partially-resolved lock was reverted. Regenerate with `uv lock` where the package index is reachable. `pyproject.toml` floors are the source of truth. |
| D5 | Spec Out-of-Scope | Low | Backfill/readiness handling (`SearchVectors` raises `ValidationException` while an index backfills and briefly after ACTIVE) | Documented caveat only; callers must retry. No wait/retry helper was built, by design. |

## Suggested Follow-up
- **D1 + D3** are the natural next iteration: a coordinated EasySAM change that both generates
  the `VectorIndexes` CloudFormation resource and settles billing-mode enforcement end-to-end.
- **D2** (multi-line decorator stripping) is a small, self-contained generator robustness fix
  worth a standalone seed.
- **D4** is operational: regenerate and commit `uv.lock` in a networked environment.
