---
generated-by: "Split Tasks"
source: docs/specs/vector-search.md
generated-at: 2026-11-07T18:00:00+02:00
inputs-ready: false
completed: false
status: not-started
---

# Task 02: Add `get_client()` to `DynamoAccess` + default implementation

- [ ] **Completion**
- **Source spec**: `docs/specs/vector-search.md`
- **Depends on**: `None`
- **Blocks**: `task-03-dynamo-vectors.md`
- **Parallelism**: `Safe with task-01, task-03` (distinct files)

## Objective
Expose the low-level boto3 DynamoDB **client** through the access layer so vector search
(`SearchVectors`, a client-only API) can reach it, while existing custom-access classes inherit
the capability unchanged.

## Scope & Traceability
- **Requirements / acceptance criteria**: Spec "Requirements" — "Add `get_client()` to the
  `DynamoAccess` base with a concrete default deriving from `self.get_resource().meta.client`".
- **Testing & risk strategy items**: Spec Task 2 tests (stub subclass returns client; subclass
  overriding only `get_resource` still inherits `get_client`).
- **Out of scope**: Using the client (Task 3); any `search_vectors` capability checks (Task 3).

## Implementation Guidance
- **Files to create or modify**:
  - `src/prismarine/runtime/dynamo_access.py`: `DynamoAccess` currently has `...`-stub methods
    (`get_resource`, `get_table`). Add a **concrete default** `get_client()` that derives from
    the resource so existing subclasses inherit it without overriding:
    `def get_client(self): return self.get_resource().meta.client`. Type the return with the
    types-boto3 DynamoDB client type if available
    (`from types_boto3_dynamodb import DynamoDBClient`) — the module already imports
    `ServiceResource`/`Table` from `types_boto3_dynamodb`. If the client type symbol is not
    exported by the pinned stub version, annotate loosely (no hard failure) and leave a comment.
  - `src/prismarine/runtime/dynamo_default.py`: `DefaultDynamoAccess` inherits `get_client()`
    automatically (it defines a real `get_resource()` returning `boto3.resource('dynamodb')`).
    Only add an explicit override if the default is insufficient; default is preferred so the
    custom-access example keeps working untouched.
- **Data/API/UI behaviour**: `resource.meta.client` is the boto3 low-level client bound to the
  same session/region as the resource — the correct handle for `search_vectors`.
- **Established patterns to follow**: `dynamo_default.py:6-12` for the resource/table impls;
  keep the base class stub-style but make `get_client` concrete (it has a universal derivation).
- **Constraints and non-goals**: Do not import numpy or call `search_vectors` here. Must not
  change `get_resource`/`get_table` behaviour or signatures. `example/myapp-custom-access`
  (`dynamo_access.py`) must keep working with no edit required.

## Verification Requirements
- **Automated tests**: Add `tests/test_dynamo_access_get_client.py`. Cases:
  - A stub subclass whose `get_resource()` returns a fake object with a `.meta.client`
    attribute → `get_client()` returns exactly that client.
  - A subclass overriding **only** `get_resource` still returns the right client via the
    inherited `get_client` (simulates custom-access inheritance).
  - Use a lightweight fake (`types.SimpleNamespace(meta=SimpleNamespace(client=sentinel))`);
    no real boto3/AWS calls.
- **Manual / integration checks**: `DefaultDynamoAccess().get_client()` returns a boto3
  dynamodb client object (offline: assert it has a `search_vectors`-or-not attribute is a Task 3
  concern; here just assert it is the `.meta.client` of the resource).
- **Risk coverage**: Ensures custom-access users (Decision 4-a) inherit the client without code
  changes.
- **Demo command**: `uv run pytest tests/test_dynamo_access_get_client.py -q`
- **Expected result**: Both inheritance cases return the sentinel client.

## Handoff Notes
Task 3's `_search_vectors` takes a `DynamoAccess` and calls `dynamo.get_client().search_vectors(...)`.
It must not assume `DefaultDynamoAccess` — any `DynamoAccess` subclass with a working
`get_resource` now yields a client.
