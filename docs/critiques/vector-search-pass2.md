---
status: applied
target: docs/specs/vector-search.md
target-revision: 2d96684b01589a66c9e433e7d43d472240d0e39f
---

# Specification Critique (Pass 2): DynamoDB Native Vector Search Support

**Target Specification**: `docs/specs/vector-search.md`  
**Prior Critique**: `docs/critiques/vector-search.md` (applied 2026-10-31)  
**Date**: 2026-11-07  
**Verdict**: ⚠️ **PROCEED WITH UPDATES**

> **Status (applied 2026-10-31):** All findings below — 6 Must-Address (X1, E1, P1, E2, X2,
> E3) and 4 Recommendations (P2, E4, E5, E6) — have been folded into
> `docs/specs/vector-search.md`. E3 was resolved via the Optional-vector-field approach. The
> sections below are retained as the review record.

---

## Executive Summary

This second specification-level critique reviews `docs/specs/vector-search.md` following the incorporation of initial critique remediations (E1, P1, X1, E2, E3, and P2). The core architectural direction remains sound: encapsulating low-level client logic within `src/prismarine/runtime/dynamo_vectors.py`, preserving byte-identical code generation for non-vector models, keeping core installations NumPy-free, and generating type-safe model query methods.

However, this adversarial review identified **6 Must-Address items (🎯)** and **4 Recommendations (💡)**. Crucially, two of the critical issues were directly introduced by the initial round of remediations:
1. **API Hallucination of Pagination (`NextToken`)**: Remediation X1 introduced `next_token` to `search()`, `SearchResults`, and `_search_vectors`. Amazon DynamoDB's `SearchVectors` API does not support pagination and has no `NextToken` parameter; passing it causes immediate runtime `ParamValidationError` failures in Boto3.
2. **Disconnected Pre-flight Dimension Validation**: Remediation E2 defined dimension validation in `_format_vector(vector, dimensions=None)`, but `dimensions` was omitted from the signature of `_search_vectors` and the generated `search()` call, leaving pre-flight validation permanently bypassed.
3. **Keyword Collision via Casing Mismatch**: Remediation P1 validated reserved parameter names without case normalisation. Because model fields are conventionally PascalCase (e.g. `Vector`) and rendered as `snake(attr)` in parameters, collisions produce unhandled duplicate parameter syntax errors.
4. **Data Model Conflation in `SearchResults[T]`**: The specification defines `SearchResults` as holding `item: T` and `score: float`, conflating an individual scored hit with the multi-hit result collection.
5. **Omission of `expression_names` Escape Hatch and Unescaped Projections**: Callers cannot alias DynamoDB reserved keywords in escape-hatch condition expressions or projection lists.
6. **Omitted Embedding Attributes in Search Responses Breaking Pydantic Hydration**: DynamoDB's `SearchVectors` API omits embedding attributes by default, triggering Pydantic validation failures when mandatory model fields are missing.

Addressing these items will align the specification with actual AWS DynamoDB wire semantics and prevent runtime failures.

---

## Product Lens Review

### 1a. Problem Validation
- **Clarity & Scope**: The boundary remains well-defined. Embedding generation remains external, whilst storage and retrieval leverage native DynamoDB vector indexing.
- **Pagination Misalignment (Finding X1)**: The addition of `next_token` in Pass 1 creates a false user expectation. DynamoDB vector searches are capped at `TopK <= 100` and do not paginate. Advertising pagination in the client API will mislead developers designing multi-page search experiences.

### 1b. User Value Assessment
- **Result Usability & Collection Ergonomics (Finding E2)**: `SearchResults[T]` cannot be used effectively as specified. Because `search()` returns up to `TopK` results, returning a single `item: T` and `score: float` fails to expose multiple matches. Users require an iterable collection of scored hits alongside metadata such as `consumed_capacity`.
- **Parameter Ordering & Developer Experience (Finding P2)**: The generated `search()` staticmethod signature places optional `top_k: int = 10` before mandatory partition key arguments (e.g. `category: str`). While syntactically valid in Python keyword-only signatures, placing optional parameters before required arguments degrades autocompletion and invocation clarity.

### 1c. Alternative Approaches
- **Collection Types**: Rather than returning a raw list of dictionaries, exposing a dedicated `SearchResults[T]` collection holding `VectorSearchResult[T]` hits preserves type safety across both TypedDict and Pydantic modes whilst accommodating future response metadata.

### 1d. Edge Cases & User Experience
- **Reserved Parameter Collision via PascalCase Fields (Finding P1)**:
  Prismarine models conventionally declare attributes in PascalCase (e.g. `Vector`, `TopK`). While Task 1 checks attributes against `{'vector', 'top_k', ...}`, it performs an exact string match. At client generation, `model.mako` converts field names using `snakecase()`. An attribute named `Vector` passes registration validation but generates `def search(*, vector, vector: str, ...)`, causing Python to raise `SyntaxError: duplicate argument 'vector' in function definition`.
- **Condition Expression Name Aliasing (Finding X2)**:
  If a user constructs an escape-hatch condition expression referencing reserved DynamoDB keywords (e.g. `status`, `year`, `type`), they cannot provide `#alias` mappings because `search()` accepts `expression_values` but omits `expression_names`.

### 1e. Success Measurement
- The specification should require explicit verification tests ensuring that generated client signatures compile cleanly for models with attributes sharing case variations of reserved names, and that returned result sets accurately preserve individual scores for all returned items.

---

## Engineering Lens Review

### 2a. Architecture Soundness
- **Runtime Separation**: Centralising vector logic in `src/prismarine/runtime/dynamo_vectors.py` maintains clean separation from core CRUD operations.
- **Plumbing Gap in Dimension Validation (Finding E1)**:
  Task 3 updates `_format_vector(vector, dimensions=None)` to validate vector dimensionality. However, the signature specified for `_search_vectors(...)` in Task 3 omits `dimensions`, and Task 4 does not pass `dimensions` from `ByEmbedding.search()`. Consequently, `dimensions` is never supplied to `_format_vector` at query time, rendering pre-flight dimension validation ineffective.
- **Result Data Model Architecture (Finding E2)**:
  Task 3 describes `SearchResults`/`VectorSearchResult` as `(item: T, score: float, next_token, consumed_capacity)`. A distinct two-tier structure is technically required:
  - `VectorSearchResult[T]`: represents an individual match with `item: T` and `score: float`.
  - `SearchResults[T]`: represents the container response with `hits: list[VectorSearchResult[T]]`, `consumed_capacity: dict[str, Any] | None`, and sequence protocols (`__iter__`, `__len__`, `__getitem__`).

### 2b. Failure Mode Analysis
- **Boto3 Parameter Validation Failure on `NextToken` (Finding X1)**:
  In `boto3.client('dynamodb').search_vectors`, `NextToken` is not a recognised request parameter. Passing `NextToken=None` or a string causes Boto3's `ParamValidationError` before any request is dispatched to AWS.
- **Pydantic Deserialisation Crash on Omitted Embeddings (Finding E3)**:
  DynamoDB's `SearchVectors` API omits the indexed embedding attribute from returned items by default to minimise payload size. Line 40 of the specification assumes embeddings are returned ("The embedding attribute is not stripped from results"). In Pydantic mode, `_load_model(Product, item)` will raise a Pydantic `ValidationError` because `Product` specifies `Embedding: list[float]` without a default value.
- **DynamoDB ValidationException on Unaliased Projections (Finding X2)**:
  If a user specifies `projection=['status', 'name']`, and `_search_vectors` constructs `ProjectionExpression=', '.join(projection)` without placeholder substitution in `ExpressionAttributeNames`, DynamoDB rejects the query if any projected attribute is a DynamoDB reserved word.

### 2c. Security & Privacy Review
- Auto-generated condition placeholders (`#pv_k_0`, `:pv_v_0`) correctly isolate equality filters from user-supplied expressions.

### 2d. Performance & Scalability
- **Quota Validation (Finding E4)**:
  DynamoDB enforces strict constraints: `TopK` cannot exceed 100, and `dimensions` must be a positive integer up to 4096. Performing pre-flight checks (`1 <= top_k <= 100`, `1 <= dimensions <= 4096`) prevents unnecessary network round-trips for invalid requests.

### 2e. Testing Strategy
- The test suite must include:
  1. Verification that passing `dimensions` through `ByEmbedding.search()` catches dimension mismatches locally before calling the Boto3 client.
  2. Verification that Pydantic models with vector attributes instantiate cleanly from `search_vectors` responses when the embedding attribute is absent.
  3. Verification that models with PascalCase attributes (e.g. `Vector`, `TopK`) are caught at registration time rather than generating invalid Python syntax.
  4. Mock testing of `SearchResults` iterating over multiple hits with distinct scores and accessing `consumed_capacity`.

### 2f. Operational Readiness
- Removing `next_token` and documenting DynamoDB's 16 MB response ceiling ensures callers design appropriate projection strategies rather than expecting cursor pagination.

### 2g. Dependencies & Integration Risks
- **EasySAM Attribute Definition Pollution (Finding E5)**:
  Task 5 specifies adding `hash` and `filters` attributes to the `attributes` dictionary in `src/prismarine/prisma_easysam.py`. In CloudFormation DynamoDB templates, `AttributeDefinitions` may only contain attributes serving as partition or sort keys for the table or GSIs/LSIs. Including arbitrary filter attributes can cause CloudFormation deployment failures.
- **Typing Stubs Floor (Finding E6)**:
  While `boto3 >= 1.43.89` is added to optional dependencies, `types-boto3[dynamodb] >= 1.38.19` in base dependencies lacks typing definitions for `search_vectors`, causing static type-checking diagnostics.

---

## Transversal Insights

- **X1: Phantom Pagination vs Native DynamoDB Semantics (Product Value × Engineering Reliability)**:
  The first critique pass recommended adding `next_token` under the assumption that DynamoDB vector search mirrors GSI query pagination. However, native `SearchVectors` does not support cursors or pagination tokens. Removing `next_token` eliminates an immediate Boto3 runtime crash and prevents misleading API design.
- **X2: Reserved Word Collisions and Expression Escapes (DX × Robustness)**:
  Both auto-generated filters and user-supplied expressions interact with DynamoDB's extensive list of reserved words. Providing `expression_names` alongside `expression_values` and automatically aliasing projection attributes ensures robust query construction across all schema definitions.

---

## Findings Summary Table

| ID | Lens | Severity | Category | Finding | Suggestion |
|----|------|----------|----------|---------|------------|
| X1 | Both | 🎯 | Failure Modes / API Validity | `SearchVectors` API does not support pagination. Supplying `NextToken` causes Boto3 `ParamValidationError`. | Remove `next_token` from `search()`, `SearchResults`, `_search_vectors`, and reserved parameter checks. Document the 100 `top_k` limit. |
| E1 | Engineering | 🎯 | Architecture Soundness | `dimensions` is omitted from `_search_vectors` and generated `search()` calls, bypassing pre-flight dimension validation. | Add `dimensions: int \| None = None` to `_search_vectors` and pass `dimensions=${vindex['dimensions']}` from `model.mako`. |
| P1 | Product | 🎯 | Edge Cases & UX | Case mismatch in reserved keyword validation allows attributes like `Vector` to pass registration but fail code generation with `SyntaxError`. | Normalise attribute names via `snakecase()` before comparing against the reserved keyword set in `@c.vector_index`. |
| E2 | Engineering | 🎯 | Architecture / Data Model | `SearchResults[T]` is defined with single `item: T` and `score: float`, unable to represent multi-item `top_k` results. | Split into `VectorSearchResult[T]` (single match) and `SearchResults[T]` (collection container with sequence methods). |
| X2 | Both | 🎯 | Architecture Soundness | `search()` omits `expression_names`, preventing attribute aliasing for reserved DynamoDB keywords in expressions and projections. | Add `expression_names: dict[str, str] \| None = None` to `search()`, merge with internal aliases, and alias projection attributes. |
| E3 | Engineering | 🎯 | Failure Modes / Hydration | DynamoDB omits embedding attributes in search responses, causing Pydantic `ValidationError` when models have required vector fields. | Explicitly project the embedding attribute when required, or specify that vector fields on models should default to `None`. |
| P2 | Product | 💡 | API Ergonomics | Generated `search()` signature places optional `top_k=10` before mandatory HASH partition key arguments. | Place required arguments (`vector`, required HASH) before optional arguments (`top_k`, filters, expressions). |
| E4 | Engineering | 💡 | Failure Modes / Validation | Missing range checks on `dimensions` (`1 <= dimensions <= 4096`) and `top_k` (`1 <= top_k <= 100`). | Add explicit pre-flight bounds validation in `@c.vector_index` and `_search_vectors`. |
| E5 | Engineering | 💡 | Integration / EasySAM | Registering non-key filter attributes in EasySAM `attributes` violates CloudFormation DynamoDB `AttributeDefinitions` rules. | Only register table and index key attributes in `attributes`. Assert or enforce `billingmode: 'PAY_PER_REQUEST'` when vector indexes exist. |
| E6 | Engineering | 💡 | Dependencies & Typing | `types-boto3[dynamodb]` version floor in base dependencies does not reflect `search_vectors` support. | Update `types-boto3[dynamodb] >= 1.43.89` in optional or development dependencies. |

---

## Verdict

⚠️ **PROCEED WITH UPDATES**

The design remains well-conceived, but the specification must be updated to address the 6 Must-Address findings—particularly removing the hallucinated `NextToken` pagination parameter, connecting `dimensions` to runtime validation, separating single hits from the result collection, and safeguarding Pydantic deserialisation against omitted vector attributes.

---

## Recommended Remediation Edits

### Remediation 1: Remove Hallucinated Pagination (`NextToken`) (Fixes X1)
In `docs/specs/vector-search.md`:
- Under **Requirements**, remove references to `next_token` parameter passing and pagination tokens.
- In **Task 1**, remove `'next_token'` from the reserved keyword set.
- In **Task 3**, remove `next_token` from `_search_vectors` arguments and return payloads.
- In **Task 4**, remove `next_token` from generated `search()` signatures and calls.
- In **Constraints to respect**, document that DynamoDB native vector search does not support pagination and enforces a maximum `TopK` of 100.

### Remediation 2: Wire Dimension Validation to Runtime (Fixes E1)
In **Task 3** and **Task 4**:
- Update `_search_vectors` signature in Task 3 to accept `dimensions: int | None = None` and pass it to `_format_vector(vector, dimensions=dimensions)`.
- Update Task 4 so that `model.mako` passes `dimensions=${vindex['dimensions']}` in the generated staticmethod call to `_search_vectors`.

### Remediation 3: Case-Insensitive Reserved Keyword Check (Fixes P1)
In **Task 1**:
- Update decorator validation to compare `snakecase(attr)` against the reserved parameter set `{'vector', 'top_k', 'condition_expression', 'expression_values', 'expression_names', 'projection', 'return_consumed_capacity'}`.

### Remediation 4: Refine `SearchResults` Data Model (Fixes E2)
In **Requirements** and **Task 3**:
- Define `VectorSearchResult[T]` as a generic container with `item: T` and `score: float`.
- Define `SearchResults[T]` as a generic collection containing `hits: list[VectorSearchResult[T]]` and `consumed_capacity: dict[str, Any] | None = None`, implementing `__iter__`, `__len__`, and `__getitem__` forwarding to `hits`.

### Remediation 5: Support `ExpressionAttributeNames` and Projections (Fixes X2)
In **Task 3** and **Task 4**:
- Add `expression_names: dict[str, str] | None = None` to `search()` and `_search_vectors`.
- In `_search_vectors`, merge caller-supplied `expression_names` with auto-generated condition placeholders (`#pv_k_i`).
- For `projection`, alias each projected attribute to namespaced placeholders (e.g. `#pv_proj_i`) in `ExpressionAttributeNames` to avoid keyword collisions.

### Remediation 6: Safeguard Pydantic Hydration for Omitted Vectors (Fixes E3)
In **Requirements** and **Task 4**:
- Clarify that DynamoDB omits embedding vectors from search results unless explicitly projected.
- Specify that `_load_model` in Pydantic mode must allow missing embedding attributes (e.g. by recommending models specify `Embedding: list[float] | None = None`, or providing a partial hydration fallback in generated clients).
