# Specification Critique: DynamoDB Native Vector Search Support

**Target Specification**: `docs/specs/vector-search.md`  
**Derived Seed**: `docs/seed/vector-search.md`  
**Date**: 2026-09-21  
**Verdict**: ⚠️ **PROCEED WITH UPDATES**

---

## Executive Summary

The specification `docs/specs/vector-search.md` presents a well-structured design to integrate DynamoDB's native `SearchVectors` API into Prismarine. It maintains Prismarine's core principles: keeping the core library `numpy`-free, supporting both `typed-dict` and `pydantic` models, preserving byte-identical code generation for non-vector models, and exposing clean, type-safe generated query interfaces.

However, the critique identified **2 Must-Address items** and **4 Recommendations** across the Product and Engineering lenses:
1. **Low-Level AttributeValue Serialization (Engineering - Critical)**: Low-level `boto3` client calls (`client.search_vectors`) require `ExpressionAttributeValues` to be formatted as `AttributeValue` maps (e.g. `{"S": "value"}`). Passing raw Python types causes boto3 parameter validation errors.
2. **Reserved Parameter Keyword Collisions (Product - Critical)**: If a model's HASH or filter attribute shares a name with reserved parameters in `search()` (`vector`, `top_k`, `projection`, etc.), generated staticmethod signatures will break.
3. **Pagination & Consumed Capacity (Cross-Lens)**: Missing `NextToken` and `ConsumedCapacity` in `SearchResults` limits production usability and cost observability.
4. **Pre-flight Runtime Dimension & Value Validation (Engineering)**: Lack of local vector length and NaN/Inf validation results in unnecessary failed network calls to AWS.
5. **Expression Attribute Namespace Isolation (Engineering)**: Auto-generated condition placeholders must be safely namespaced to prevent collisions with user escape-hatch expressions.
6. **Filter Parameter Type Hints (Product)**: Filter argument type hints should be derived from the model schema rather than hardcoding `str`.

Addressing these items prior to implementation will prevent runtime errors and ensure a robust implementation.

---

## Product Lens Review

### 1a. Problem Validation
- **Clarity & Need**: The problem statement is well-scoped and addresses a real requirement: enabling vector similarity queries via DynamoDB's native capability without requiring external vector databases or introducing `numpy` dependencies to core CRUD users.
- **Boundary & Scope**: Clear separation of responsibilities—Prismarine handles storage/search API abstraction, while embedding generation remains the caller's responsibility.

### 1b. User Value Assessment
- **Value Delivery**: The proposed `@c.vector_index` decorator and generated `ByEmbedding.search()` method fit naturally into Prismarine's existing pattern for GSIs (`@c.index`).
- **Gaps in Returned Data**:
  - **Consumed Capacity**: Production applications need visibility into DynamoDB RCU costs for vector queries.
  - **Pagination (`NextToken`)**: Users querying top-K vectors across paginated data need access to `NextToken`.

### 1c. Alternative Approaches
- **Low-level boto3 client vs. Abstraction**: Generating typed `search()` methods inside model classes provides ideal developer ergonomics while hiding low-level payload construction.

### 1d. Edge Cases & User Experience
- **Attribute Name Collisions (Finding P1)**:
  - If a model's table schema has a filter or HASH attribute named `vector`, `top_k`, `condition_expression`, `expression_values`, `projection`, or `next_token`, keyword collisions will occur in the generated `search()` staticmethod.
- **Type Safety of Filter Kwargs (Finding P2)**:
  - Hardcoding `str` for filter kwargs in `model.mako` will produce incorrect type hints when filter fields are integers, floats, or enums in the model definition.

### 1e. Success Measurement
- The spec currently lacks concrete testing metrics for latency overhead and memory footprint during low-level payload deserialization.

---

## Engineering Lens Review

### 2a. Architecture Soundness
- **Separation of Concerns**: Confining `numpy` duck-typing and low-level client logic to `src/prismarine/runtime/dynamo_vectors.py` keeps `src/prismarine/runtime/dynamo_crud.py` and core client generator clean.
- **Access Layer Integration**: Extending `DynamoAccess` with `get_client()` in `src/prismarine/runtime/dynamo_access.py` allows standard and custom access layers to provide `meta.client`.

### 2b. Failure Mode Analysis
- **Low-Level AttributeValue Serialization (Finding E1)**:
  - `boto3.client('dynamodb').search_vectors` is a low-level client API. Unlike `Table.query()`, `client.search_vectors()` requires `ExpressionAttributeValues` to use low-level DynamoDB `AttributeValue` descriptors (e.g. `{\":brand\": {\"S\": \"Nike\"}}`).
  - Passing plain Python values (`brand="Nike"`) directly to `client.search_vectors` will trigger a boto3 `ParamValidationError`. `TypeSerializer` must be used.
- **Pre-flight Vector Validation (Finding E2)**:
  - Passing a vector whose length does not match `dimensions`, or passing `NaN`/`Inf` floats, causes AWS API failures after network latency. `_format_vector` must validate floats and vector length locally.
- **Placeholder Namespace Isolation (Finding E3)**:
  - Auto-generated placeholder keys (`#k`, `:k`) for equality conditions must use unique prefixes (e.g., `#pv_k_0`, `:pv_v_0`) to prevent collisions with user-supplied escape-hatch `expression_values`.

### 2c. Security & Privacy Review
- Escape-hatch expressions (`condition_expression`) rely on standard DynamoDB parameterization via `expression_values`, mitigating injection risks when properly parameterized.

### 2d. Performance & Scalability
- Vector formatting duck-types `.tolist()` and formats items into `[{"N": str(x)}]`. Pre-flight validation adds negligible overhead (< 1ms) compared to network RPC.

### 2e. Testing Strategy
- Unit tests must cover:
  1. Low-level `TypeSerializer` formatting for equality filter kwargs and `expression_values`.
  2. Reserved parameter validation during `@c.vector_index` registration.
  3. Pre-flight dimension mismatch and `NaN`/`Inf` error handling.
  4. Pagination token (`NextToken`) and consumed capacity passthrough.

### 2f. Operational Readiness
- `SearchResults` should include `consumed_capacity` and `next_token` to support ops monitoring and large-result pagination.

### 2g. Dependencies & Integration Risks
- `boto3 >= 1.43.89` version floor is correctly specified.

---

## Cross-Lens Synthesis

- **X1: Pagination & Consumed Capacity (User Value × Operational Readiness)**:
  - **Product Perspective**: Users need `NextToken` to paginate vector search results beyond a single request.
  - **Engineering Perspective**: Ops teams require `ConsumedCapacity` metrics to monitor DynamoDB RCU costs.
  - **Convergence**: Enhancing `search()` and `SearchResults` with `next_token` and `consumed_capacity` satisfies both user UX and operational requirements with minimal additional complexity.

---

## Findings Summary Table

| ID | Lens | Severity | Category | Finding | Suggestion |
|----|------|----------|----------|---------|------------|
| E1 | Engineering | 🎯 | Low-Level API Serialization | `client.search_vectors` requires low-level DynamoDB `AttributeValue` maps in `ExpressionAttributeValues`. Passing raw Python types causes boto3 `ParamValidationError`. | Use `boto3.dynamodb.types.TypeSerializer().serialize(val)` in `_search_vectors` for all filter values and `expression_values`. |
| P1 | Product | 🎯 | Edge Cases & UX | Reserved keyword collision in generated `search()` staticmethod if model attribute matches `vector`, `top_k`, `projection`, etc. | Validate reserved keywords in `@c.vector_index` registration and raise error if `hash` or `filters` collide. |
| X1 | Both | 💡 | Scope × Risk | `SearchResults` omits `next_token` and `consumed_capacity`, blocking pagination and cost monitoring. | Add `next_token` and `return_consumed_capacity` to `search()`, and include `next_token` and `consumed_capacity` in `SearchResults`. |
| E2 | Engineering | 💡 | Failure Modes | Mismatched vector dimensions or `NaN`/`Inf` values fail at AWS API level after network round-trip. | Validate vector length against `dimensions` and ensure values are finite in `_format_vector` before calling AWS. |
| E3 | Engineering | 💡 | Architecture Soundness | Auto-generated expression placeholders (`#k`, `:k`) can collide with user-supplied escape-hatch `expression_values`. | Use unique prefixes (e.g. `#pv_k_0`, `:pv_v_0`) for auto-generated equality placeholders. |
| P2 | Product | 💡 | Type Safety | Generated `search()` filter kwargs hardcode `str` type hint instead of using model field types. | Look up model field types in `model.mako` when rendering `search()` filter parameter annotations. |
| P3 | Product | 🤔 | Problem Validation | Assumes fixed static limits (PAY_PER_REQUEST, <=5 indexes per table, dimensions <= 4096). | Clarify static vs table-level validation scope between Prismarine core and EasySAM. |

---

## Verdict

⚠️ **PROCEED WITH UPDATES**

The specification is overall high quality and ready for implementation once the Must-Address findings (E1 and P1) and key Recommendations (X1, E2, E3, P2) are incorporated into `docs/specs/vector-search.md`.

---

## Recommended Remediation Edits

Below are the exact suggested edits for `docs/specs/vector-search.md`:

### Remediation 1 (Fixes E1, E2, E3, X1 in Task 3 & Requirements):
Update **Requirements** and **Task 3** in `docs/specs/vector-search.md`:
- Clarify that `_search_vectors` uses `TypeSerializer` from `boto3.dynamodb.types` to wrap equality filter values and `expression_values` into low-level `AttributeValue` maps (`{"S": ...}`, `{"N": ...}`).
- Specify pre-flight validation in `_format_vector`: check `len(vector) == dimensions` (when dimensions provided) and assert finite numbers (`math.isfinite(x)`).
- Update `SearchResults[T]` to include `next_token: str | None = None` and `consumed_capacity: dict[str, Any] | None = None`.
- Add `next_token: str | None = None` and `return_consumed_capacity: str | None = None` kwargs to `search()`.

### Remediation 2 (Fixes P1 in Task 1 & Requirements):
Update **Task 1** (`vector_index` decorator):
- Add validation in `@c.vector_index` against reserved parameter names: `{'vector', 'top_k', 'condition_expression', 'expression_values', 'projection', 'next_token', 'return_consumed_capacity'}`. Raise `ValueError` if `hash` or any attribute in `filters` matches a reserved name.

### Remediation 3 (Fixes P2 in Task 4 & Proposed Solution):
Update **Task 4** and **Generated method sketch**:
- Render kwarg type annotations for `hash` and `filters` in `model.mako` based on the corresponding field type in the model schema rather than hardcoding `str`.

---

Would you like me to apply these changes to `docs/specs/vector-search.md`? (all / select / none)
