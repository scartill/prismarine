from typing import TypedDict, NotRequired, Literal

from caseconverter import snakecase


class TriggerConfig(TypedDict):
    """DynamoDB Stream Trigger Configuration for EasySAM"""

    function: str
    viewtype: NotRequired[Literal['keys-only', 'new', 'old', 'new-and-old']]
    batchsize: NotRequired[int]
    batchwindow: NotRequired[int]
    startingposition: NotRequired[Literal['trim-horizon', 'latest']]


class VectorIndexConfig(TypedDict):
    """DynamoDB Native Vector Index Configuration"""

    index: str
    attribute: str
    dimensions: int
    distance: Literal['COSINE', 'EUCLIDEAN', 'DOT_PRODUCT']
    hash: NotRequired[str]
    filters: NotRequired[list[str]]


class Cluster:
    prefix: str
    models: list[dict]
    exports: dict[str, dict]

    def __init__(self, prefix=''):
        self.prefix = prefix
        self.models = []
        self.exports = {}

    def model(
        self,
        *,
        PK: str,
        SK: str | None = None,
        table: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        trigger: str | TriggerConfig | None = None,
        ttl: str | None = None,
    ):
        def decorator(cls):
            model_data = {
                'cls': cls,
                'main': {'PK': PK, 'SK': SK},
                'table': table or self.prefix + (name or cls.__name__),
                'indexes': {},
                'vector_indexes': {},
                'class_name': cls.__name__,
                'name': name,
            }

            # Add trigger if specified
            if trigger:
                model_data['trigger'] = trigger

            # Add TTL if specified
            if ttl:
                model_data['ttl'] = ttl

            self.models.append(model_data)
            return cls

        return decorator

    def index(self, *, index: str, PK: str, SK: str | None = None):
        def decorator(cls):
            model = next((m for m in self.models if m['cls'] == cls), None)
            if not model:
                raise Exception('Model not found. Index decorator must be placed above model decorator')

            model['indexes'][index] = {'PK': PK, 'SK': SK}
            return cls

        return decorator

    def vector_index(
        self,
        *,
        index: str,
        attribute: str,
        dimensions: int,
        distance: str,
        hash: str | None = None,
        filters: list[str] | None = None,
    ):
        if distance not in {'COSINE', 'EUCLIDEAN', 'DOT_PRODUCT'}:
            raise ValueError(f"Invalid distance '{distance}'. Must be one of: COSINE, EUCLIDEAN, DOT_PRODUCT")

        if not (1 <= dimensions <= 4096):
            raise ValueError(f'Invalid dimensions {dimensions}. Must be between 1 and 4096 (inclusive)')

        reserved = {
            'vector',
            'top_k',
            'condition_expression',
            'expression_values',
            'expression_names',
            'projection',
            'return_consumed_capacity',
            'results',
            'hash_conditions',
            'filter_conditions',
        }

        attrs = []
        if hash is not None:
            attrs.append(hash)
        attrs.extend(filters or [])

        seen: set[str] = set()
        for attr in attrs:
            normalized = snakecase(attr)
            if normalized in reserved:
                raise ValueError(
                    f"Attribute '{attr}' collides with a reserved name "
                    f"('{normalized}') used by the generated search method"
                )
            if normalized in seen:
                raise ValueError(
                    f"Attribute '{attr}' collapses to a duplicate name '{normalized}' "
                    f'already used by another hash/filter attribute'
                )
            seen.add(normalized)

        def decorator(cls):
            model = next((m for m in self.models if m['cls'] == cls), None)
            if not model:
                raise Exception('Model not found. Index decorator must be placed above model decorator')

            model['vector_indexes'][index] = {
                'attribute': attribute,
                'dimensions': dimensions,
                'distance': distance,
                'hash': hash,
                'filters': filters or [],
            }

            if len(model['vector_indexes']) > 5:
                raise ValueError('DynamoDB permits at most 5 vector indexes per table')

            return cls

        return decorator

    def export(self, cls):
        self.exports[cls.__name__] = {'cls': cls, 'class_name': cls.__name__}
        return cls
