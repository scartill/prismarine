# Code Review: DynamoDB Native Vector Search Support

**Reviewed**: 2026-11-07  
**Author**: Boris Resnick <boris.resnick@gmail.com>  
**Branch**: `vector-indices` → `main`  
**Decision**: REQUEST CHANGES  

> **Status (applied 2026-11-07):** All three HIGH findings were fixed and verified
> (float→Decimal via `serialize_item`; parenthesized `condition_expression`;
> `inspect.formatannotation` for generic type hints). The three MEDIUM findings were also
> applied (reserved `dynamo`, `keyword.iskeyword` check, `#pv_`/`:pv_` namespace-collision
> guard) along with the LOW deterministic EasySAM ordering. The remaining LOW (multi-line
> decorator stripping) is an accepted pre-existing generator limitation, recorded for
> follow-up. Suite: 54 passed, 1 skipped; lint clean.

## QA & Verification Guidance

- **Risk Assessment & Migration Notes**:
  - Requires boto3 >= 1.43.89 to run native vector searches against DynamoDB (`search_vectors` API).
  - Core Prismarine remains numpy-free; callers utilizing numpy arrays must install `prismarine[vectors]`.
  - DynamoDB vector indexes necessitate tables in on-demand mode (`PAY_PER_REQUEST`). CloudFormation deployment via EasySAM requires accompanying EasySAM support for the emitted `vectorindices` block.
  - Generated clients omit vector runtime imports when no `@c.vector_index` decorator is registered, guaranteeing backwards-compatible, byte-identical output for non-vector models.
- **Behavioral Changes to Verify**:
  - Models decorated with `@c.vector_index` expose a nested class (e.g. `ByEmbedding`) containing a static `search()` method.
  - DynamoDB vector search responses do not paginate (`top_k` <= 100) and omit embedding attributes from items unless explicitly requested via `projection`.
  - Pydantic models hydrate search results as `SearchResults[T]` with `consumed_capacity` preserved.
- **Testing Hints for QA**:
  1. Verify searches executing with `float` attribute values in `filter_conditions`, `hash_conditions`, or `expression_values` (currently failing with `TypeError`).
  2. Verify queries combining a `hash` condition with an `OR`-based `condition_expression` to confirm partition isolation is strictly enforced.
  3. Verify client generation for models declaring `Optional[...]` or `Union[...]` fields on vector filter attributes.

## Technical Summary

The vector search implementation introduces an elegant, numpy-isolated architecture with comprehensive wire-level test coverage and cleanly generated client interfaces. However, changes are requested due to three HIGH-severity defects: native Python `float` values in filter conditions crash boto3's `TypeSerializer`, boolean operator precedence in `SearchConditionExpression` permits partition key escape when `OR` expressions are supplied, and type annotation resolution reduces generic wrappers to bare, unimported identifiers (`Optional`, `Union`) causing runtime `NameError` exceptions in generated clients.

## Findings

### CRITICAL

None

### HIGH

- **`src/prismarine/runtime/dynamo_vectors.py:104, 119` — Boto3 `TypeSerializer` Float Incompatibility Crashes Filters and Escape-Hatch Values**  
  `_search_vectors` invokes `serializer.serialize(value)` directly on items from `equalities` (composed from `hash_conditions` and `filter_conditions`) as well as `expression_values`. Standard `boto3.dynamodb.types.TypeSerializer` explicitly rejects Python `float` values with `TypeError: Float types are not supported. Use Decimal types instead.`. Because Prismarine standardises on native Python floats (e.g. `price: float = 9.5`, `score: float`), any query passing float filter values or float expression values triggers a fatal `TypeError` prior to dispatch.  
  *Recommendation*: Convert numeric values via Prismarine's existing `serialize_item` utility (`from prismarine.runtime.dynamo_crud import serialize_item`) before calling `serializer.serialize()`, which safely coerces floats into `Decimal(str(val))`.

- **`src/prismarine/runtime/dynamo_vectors.py:111` — Operator Precedence in `SearchConditionExpression` Compromises Partition Isolation on `OR` Clauses**  
  When conjunctions from `hash_conditions`/`filter_conditions` are combined with a caller-provided `condition_expression`, `_search_vectors` joins them with:  
  `search_condition = f'({search_condition}) AND {condition_expression}'`  
  In DynamoDB condition expressions, `AND` takes precedence over `OR`. If a caller supplies an expression with a disjunction (e.g. `condition_expression="status = :s1 OR status = :s2"`), the resulting condition is evaluated as:  
  `((#pv_k_0 = :pv_v_0) AND status = :s1) OR (status = :s2)`  
  Any item matching `status = :s2` will be returned across the entire table or partition index, entirely bypassing the HASH partition constraint (`#pv_k_0 = :pv_v_0`).  
  *Recommendation*: Enclose `condition_expression` in grouping parentheses: `f'({search_condition}) AND ({condition_expression})'`.

- **`src/prismarine/prisma_client.py:39` — Type Annotation Resolver Strips Generic Parameters to Bare, Unimported Identifiers**  
  `_resolve_annotation` employs `getattr(ann, '__name__', str(ann))` to derive type annotation strings for model attributes. In Python's `typing` module, typing constructs such as `typing.Optional[T]`, `typing.Union[A, B]`, and `typing.Literal[...]` expose `__name__` as `'Optional'`, `'Union'`, and `'Literal'` respectively. Consequently, `Optional[str]` resolves to `'Optional'`, which `model.mako` renders as `brand: Optional | None = None`. Because `Optional` and `Union` are not imported in `HEADER_TEMPLATE`, importing the generated client immediately raises `NameError: name 'Optional' is not defined`.  
  *Recommendation*: Avoid reading `__name__` when an annotation defines `__origin__` or is a typing generic alias; format composite annotations using `inspect.formatannotation(ann)` or clean stringification.

### MEDIUM

- **`src/prismarine/runtime/cluster.py:99-110`, `src/prismarine/model.mako:186` — Filter Named `dynamo` Shadows Module-Level Client Handle**  
  In `model.mako`, `search()` is generated as a `@staticmethod` calling `_search_vectors(dynamo, ...)`, referencing the module-level `dynamo` variable. If a model defines a filter attribute named `Dynamo` (or `dynamo`), `Cluster.vector_index` permits it because `'dynamo'` is missing from `reserved`. The generated `search()` signature then introduces `dynamo: str | None = None`, shadowing the module-level symbol. Invoking `search()` passes `None` (or the filter string) to `_search_vectors`, triggering an `AttributeError` on `.get_client()`.  
  *Recommendation*: Add `'dynamo'` to the `reserved` set in `Cluster.vector_index`.

- **`src/prismarine/runtime/cluster.py:118-130` — Python Reserved Keywords in `hash` or `filters` Evade Decorator Validation**  
  `Cluster.vector_index` validates attribute names against generated argument names, but does not validate against Python language keywords (`keyword.iskeyword`). An attribute named `Class`, `From`, `In`, or `Def` passes validation, producing invalid signatures such as `def search(*, vector, class: str, from: str | None = None)` in `model.mako`, which triggers a Python `SyntaxError` during code generation.  
  *Recommendation*: Check `keyword.iskeyword(normalized)` alongside the `reserved` set in `Cluster.vector_index`.

- **`src/prismarine/runtime/dynamo_vectors.py:115-120` — Unchecked Caller Expression Names/Values Allow Overwriting Internal Namespaces**  
  `_search_vectors` builds internal namespaced aliases (`#pv_k_{i}`, `:pv_v_{i}`, `#pv_proj_{i}`) and subsequently merges caller-supplied `expression_names` and `expression_values` into the same dictionaries without collision detection. A caller passing `expression_names={'#pv_k_0': 'Other'}` silently overwrites the partition key alias.  
  *Recommendation*: Validate that caller keys in `expression_names` and `expression_values` do not begin with `#pv_` or `:pv_`.

### LOW

- **`src/prismarine/prisma_easysam.py:56` — Non-deterministic Vector Index Ordering in EasySAM**  
  `prisma_client.py` sorts vector indexes by name (`sorted(model['vector_indexes'].items(), key=lambda x: x[0])`), ensuring deterministic output. `prisma_easysam.py` iterates `data.get('vector_indexes', {}).items()` without sorting, making CloudFormation template generation sensitive to dictionary insertion order.  
  *Recommendation*: Sort `vector_indexes` items by index name in `prisma_easysam.py`.

- **`src/prismarine/prisma_client.py:227` — Accepted Pre-existing Limitation: Multi-Line Decorator Stripping**  
  `build_client` strips decorators via `re.sub(r'@.+?\n', '', source)`. Multi-line `@c.vector_index(...)` declarations on TypedDict models leak continuation lines into the generated `UpdateDTO`. As noted by the team, this is an established generator limitation, but callers should keep decorator declarations on a single line until multi-line stripping is addressed.

## Validation Results

| Check | Result | Notes |
|---|---|---|
| Type check | Skipped | Static type checker runner not configured in repository; type definitions inspected |
| Lint | Pass | `.venv\Scripts\ruff.exe check src tests` clean with zero diagnostics |
| Tests | Pass | 48 passed, 1 skipped (`test_format_vector_numpy_array` skipped due to absent numpy in test venv) |
| Build | Skipped | Wheel build script not configured for direct local execution |

## Files Reviewed

| File | Change Type |
|---|---|
| `src/prismarine/runtime/cluster.py` | Modified |
| `src/prismarine/runtime/dynamo_access.py` | Modified |
| `src/prismarine/runtime/dynamo_vectors.py` | Added |
| `src/prismarine/prisma_client.py` | Modified |
| `src/prismarine/model.mako` | Modified |
| `src/prismarine/prisma_easysam.py` | Modified |
| `src/prismarine/runtime/__init__.py` | Modified |
| `pyproject.toml` | Modified |
| `tests/test_vector_index_decorator.py` | Added |
| `tests/test_dynamo_access_get_client.py` | Added |
| `tests/test_dynamo_vectors.py` | Added |
| `tests/test_easysam_vectorindices.py` | Added |
| `tests/test_prisma_client_generation.py` | Modified |
| `README.md` | Modified |
| `example/myapp/myobject/models.py` | Modified |
