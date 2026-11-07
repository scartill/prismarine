import math
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from prismarine.runtime.dynamo_access import DynamoAccess
from prismarine.runtime.dynamo_crud import prepare_item, serialize_item

T = TypeVar('T')


@dataclass(frozen=True)
class VectorSearchResult(Generic[T]):
    """A single vector-search hit: the deserialized item plus its raw score."""

    item: T
    score: float


@dataclass
class SearchResults(Generic[T]):
    """A collection of vector-search hits.

    The raw ``Score`` is passed through unchanged (its meaning depends on the
    distance function). There is no pagination: ``SearchVectors`` returns at most
    ``TopK`` results in a single call, so only ``consumed_capacity`` is surfaced.
    """

    hits: list[VectorSearchResult[T]] = field(default_factory=list)
    consumed_capacity: dict[str, Any] | None = None

    def __iter__(self):
        return iter(self.hits)

    def __len__(self) -> int:
        return len(self.hits)

    def __getitem__(self, index):
        return self.hits[index]


def _format_vector(vector: Any, dimensions: int | None = None) -> list[dict[str, str]]:
    """Duck-type ``vector`` into the plain ``[{"N": ...}]`` SearchVector shape.

    numpy is never imported here: if the input exposes ``.tolist()`` (e.g. a
    numpy array) we use it, otherwise we fall back to ``list(...)``. Every value
    must be finite (``NaN``/``Inf`` rejected) and, when ``dimensions`` is known,
    the length must match. Validation happens locally, before any network call.
    """
    if hasattr(vector, 'tolist'):
        values = vector.tolist()
    else:
        values = list(vector)

    for x in values:
        if not math.isfinite(float(x)):
            raise ValueError(f'Vector values must be finite; got {x!r}')

    if dimensions is not None and len(values) != dimensions:
        raise ValueError(f'Vector has {len(values)} dimensions, expected {dimensions}')

    return [{'N': str(x)} for x in values]


def _search_vectors(
    dynamo: DynamoAccess,
    table: str,
    index: str,
    *,
    vector: Any,
    top_k: int,
    dimensions: int | None = None,
    hash_conditions: dict[str, Any] | None = None,
    filter_conditions: dict[str, Any] | None = None,
    condition_expression: str | None = None,
    expression_values: dict[str, Any] | None = None,
    expression_names: dict[str, str] | None = None,
    projection: list[str] | None = None,
    return_consumed_capacity: str | None = None,
) -> SearchResults[Any]:
    """Run a native DynamoDB ``SearchVectors`` query and return a typed collection.

    ``hash_conditions`` / ``filter_conditions`` default to ``None`` so a hashless
    index can pass nothing; iteration always guards against ``None``.
    """
    if not 1 <= top_k <= 100:
        raise ValueError(f'top_k must be in [1, 100]; got {top_k}')

    search_vector = _format_vector(vector, dimensions=dimensions)

    serializer = TypeSerializer()
    deserializer = TypeDeserializer()

    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    conjunctions: list[str] = []

    equalities = list((hash_conditions or {}).items()) + list((filter_conditions or {}).items())
    for i, (attr, value) in enumerate(equalities):
        name_ph = f'#pv_k_{i}'
        value_ph = f':pv_v_{i}'
        names[name_ph] = attr
        # serialize_item coerces native floats -> Decimal(str(val)); TypeSerializer
        # rejects raw Python floats, and Prismarine standardizes on native floats.
        values[value_ph] = serializer.serialize(serialize_item(value))
        conjunctions.append(f'{name_ph} = {value_ph}')

    search_condition = ' AND '.join(conjunctions) if conjunctions else None

    if condition_expression:
        if search_condition:
            # Parenthesize the caller expression: in DynamoDB condition expressions
            # AND binds tighter than OR, so an un-grouped `OR` in condition_expression
            # would otherwise escape the partition/hash constraint.
            search_condition = f'({search_condition}) AND ({condition_expression})'
        else:
            search_condition = condition_expression

    for name, attr in (expression_names or {}).items():
        if name.startswith('#pv_'):
            raise ValueError(f'expression_names key {name!r} collides with the reserved #pv_ namespace')
        names[name] = attr

    for key, value in (expression_values or {}).items():
        if key.startswith(':pv_'):
            raise ValueError(f'expression_values key {key!r} collides with the reserved :pv_ namespace')
        values[key] = serializer.serialize(serialize_item(value))

    projection_expression = None
    if projection:
        proj_aliases: list[str] = []
        for i, attr in enumerate(projection):
            alias = f'#pv_proj_{i}'
            names[alias] = attr
            proj_aliases.append(alias)
        projection_expression = ', '.join(proj_aliases)

    request: dict[str, Any] = {
        'TableName': table,
        'IndexName': index,
        'SearchVector': search_vector,
        'TopK': top_k,
    }

    if search_condition:
        request['SearchConditionExpression'] = search_condition
    if names:
        request['ExpressionAttributeNames'] = names
    if values:
        request['ExpressionAttributeValues'] = values
    if projection_expression:
        request['ProjectionExpression'] = projection_expression
    if return_consumed_capacity is not None:
        request['ReturnConsumedCapacity'] = return_consumed_capacity

    client = dynamo.get_client()
    if not hasattr(client, 'search_vectors'):
        raise RuntimeError(
            'The installed boto3 does not support SearchVectors. Upgrade boto3 to >= 1.43.89 to use vector search.'
        )

    resp = client.search_vectors(**request)

    hits: list[VectorSearchResult[Any]] = []
    for result in resp.get('SearchResults', []):
        item = prepare_item({k: deserializer.deserialize(v) for k, v in result['Item'].items()})
        hits.append(VectorSearchResult(item=item, score=result['Score']))

    return SearchResults(hits=hits, consumed_capacity=resp.get('ConsumedCapacity'))
