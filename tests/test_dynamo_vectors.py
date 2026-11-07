import subprocess
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

from prismarine.runtime.dynamo_vectors import (
    SearchResults,
    VectorSearchResult,
    _format_vector,
    _search_vectors,
)


class FakeClient:
    """Records the request dict and returns a canned SearchVectors payload."""

    def __init__(self, payload):
        self._payload = payload
        self.request = None

    def search_vectors(self, **request):
        self.request = request
        return self._payload


class ClientWithoutSearch:
    """A client that does not support search_vectors."""


class FakeDynamoAccess:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


def _canned_payload():
    return {
        'SearchResults': [
            {
                'Item': {
                    'ProductId': {'S': 'p1'},
                    'Category': {'S': 'books'},
                    'Rank': {'N': '3'},
                    'Price': {'N': '9.5'},
                },
                'Score': 0.12,
            },
            {
                'Item': {
                    'ProductId': {'S': 'p2'},
                    'Category': {'S': 'books'},
                    'Rank': {'N': '7'},
                    'Price': {'N': '4'},
                },
                'Score': 0.87,
            },
        ],
        'ConsumedCapacity': {'TableName': 'Products', 'CapacityUnits': 2.0},
    }


# --- _format_vector ---------------------------------------------------------


def test_format_vector_plain_list():
    assert _format_vector([0.1, 0.2]) == [{'N': '0.1'}, {'N': '0.2'}]


def test_format_vector_numpy_array():
    np = pytest.importorskip('numpy')
    arr = np.array([0.1, 0.2])
    assert _format_vector(arr) == [{'N': '0.1'}, {'N': '0.2'}]


def test_format_vector_rejects_nan():
    with pytest.raises(ValueError):
        _format_vector([float('nan')])


def test_format_vector_rejects_inf():
    with pytest.raises(ValueError):
        _format_vector([float('inf')])


def test_format_vector_dimension_mismatch():
    with pytest.raises(ValueError):
        _format_vector([0.1, 0.2], dimensions=3)


def test_format_vector_dimension_match():
    assert _format_vector([0.1, 0.2], dimensions=2) == [{'N': '0.1'}, {'N': '0.2'}]


# --- top_k bounds -----------------------------------------------------------


def test_top_k_too_low_raises():
    dynamo = FakeDynamoAccess(FakeClient(_canned_payload()))
    with pytest.raises(ValueError):
        _search_vectors(dynamo, 'Products', 'by-embedding', vector=[0.1, 0.2], top_k=0)


def test_top_k_too_high_raises():
    dynamo = FakeDynamoAccess(FakeClient(_canned_payload()))
    with pytest.raises(ValueError):
        _search_vectors(dynamo, 'Products', 'by-embedding', vector=[0.1, 0.2], top_k=101)


# --- multi-hit payload: deserialization / scores / iteration / len / indexing ---


def test_search_vectors_multi_hit_results():
    client = FakeClient(_canned_payload())
    dynamo = FakeDynamoAccess(client)

    results = _search_vectors(
        dynamo,
        'Products',
        'by-embedding',
        vector=[0.1, 0.2],
        top_k=10,
        hash_conditions={'Category': 'books'},
    )

    assert isinstance(results, SearchResults)
    assert len(results) == 2

    # iteration yields VectorSearchResult hits
    hits = list(results)
    assert len(hits) == 2
    assert all(isinstance(h, VectorSearchResult) for h in hits)

    # scores preserved and distinct
    assert results[0].score == 0.12
    assert results[1].score == 0.87

    # deserialization: Decimals stripped to int/float by prepare_item
    item0 = results[0].item
    assert item0['ProductId'] == 'p1'
    assert item0['Category'] == 'books'
    assert item0['Rank'] == 3
    assert not isinstance(item0['Rank'], Decimal)
    assert item0['Price'] == 9.5

    # consumed_capacity surfaced
    assert results.consumed_capacity == {'TableName': 'Products', 'CapacityUnits': 2.0}


# --- request wire-correctness -----------------------------------------------


def test_request_serializes_values_and_namespaces_placeholders():
    client = FakeClient(_canned_payload())
    dynamo = FakeDynamoAccess(client)

    _search_vectors(
        dynamo,
        'Products',
        'by-embedding',
        vector=[0.1, 0.2],
        top_k=5,
        hash_conditions={'Category': 'books'},
        filter_conditions={'Rank': 7},
    )

    req = client.request
    names = req['ExpressionAttributeNames']
    values = req['ExpressionAttributeValues']

    # namespaced placeholders
    assert names['#pv_k_0'] == 'Category'
    assert names['#pv_k_1'] == 'Rank'
    assert req['SearchConditionExpression'] == '#pv_k_0 = :pv_v_0 AND #pv_k_1 = :pv_v_1'

    # TypeSerializer wrapping
    assert values[':pv_v_0'] == {'S': 'books'}
    assert values[':pv_v_1'] == {'N': '7'}

    # SearchVector shape + no pagination key
    assert req['SearchVector'] == [{'N': '0.1'}, {'N': '0.2'}]
    assert 'NextToken' not in req


def test_caller_expression_names_values_merge_without_collision():
    client = FakeClient(_canned_payload())
    dynamo = FakeDynamoAccess(client)

    _search_vectors(
        dynamo,
        'Products',
        'by-embedding',
        vector=[0.1, 0.2],
        top_k=5,
        hash_conditions={'Category': 'books'},
        condition_expression='#user_rank > :min_rank',
        expression_names={'#user_rank': 'Rank'},
        expression_values={':min_rank': 5},
    )

    req = client.request
    names = req['ExpressionAttributeNames']
    values = req['ExpressionAttributeValues']

    # auto placeholders coexist with caller-supplied ones
    assert names['#pv_k_0'] == 'Category'
    assert names['#user_rank'] == 'Rank'
    assert values[':pv_v_0'] == {'S': 'books'}
    # caller value serialized via TypeSerializer
    assert values[':min_rank'] == {'N': '5'}

    # escape-hatch expression appended to the namespaced auto part
    assert req['SearchConditionExpression'] == '(#pv_k_0 = :pv_v_0) AND #user_rank > :min_rank'


def test_projection_aliasing():
    client = FakeClient(_canned_payload())
    dynamo = FakeDynamoAccess(client)

    _search_vectors(
        dynamo,
        'Products',
        'by-embedding',
        vector=[0.1, 0.2],
        top_k=5,
        hash_conditions={'Category': 'books'},
        projection=['Title', 'Price'],
    )

    req = client.request
    names = req['ExpressionAttributeNames']
    assert names['#pv_proj_0'] == 'Title'
    assert names['#pv_proj_1'] == 'Price'
    assert req['ProjectionExpression'] == '#pv_proj_0, #pv_proj_1'


# --- hashless + no-filter call ----------------------------------------------


def test_hashless_no_filter_with_projection():
    client = FakeClient(_canned_payload())
    dynamo = FakeDynamoAccess(client)

    results = _search_vectors(
        dynamo,
        'Products',
        'by-embedding',
        vector=[0.1, 0.2],
        top_k=5,
        hash_conditions=None,
        filter_conditions=None,
        projection=['Title'],
    )

    assert len(results) == 2
    req = client.request
    # no conditions built
    assert 'SearchConditionExpression' not in req
    # no values map (empty) — DynamoDB rejects empty expr maps
    assert 'ExpressionAttributeValues' not in req
    # projection still present with aliased names
    assert req['ProjectionExpression'] == '#pv_proj_0'
    assert req['ExpressionAttributeNames'] == {'#pv_proj_0': 'Title'}


# --- empty-maps guard -------------------------------------------------------


def test_empty_maps_guard_no_conditions_no_projection():
    client = FakeClient(_canned_payload())
    dynamo = FakeDynamoAccess(client)

    _search_vectors(
        dynamo,
        'Products',
        'by-embedding',
        vector=[0.1, 0.2],
        top_k=5,
    )

    req = client.request
    assert 'ExpressionAttributeNames' not in req
    assert 'ExpressionAttributeValues' not in req
    assert 'SearchConditionExpression' not in req
    assert 'ProjectionExpression' not in req
    assert 'NextToken' not in req


# --- capability check -------------------------------------------------------


def test_capability_check_raises_runtime_error():
    dynamo = FakeDynamoAccess(ClientWithoutSearch())
    with pytest.raises(RuntimeError):
        _search_vectors(
            dynamo,
            'Products',
            'by-embedding',
            vector=[0.1, 0.2],
            top_k=5,
        )


def test_capability_check_accepts_simplenamespace_with_search():
    payload = _canned_payload()
    recorded = {}

    def search_vectors(**request):
        recorded.update(request)
        return payload

    client = SimpleNamespace(search_vectors=search_vectors)
    dynamo = FakeDynamoAccess(client)
    results = _search_vectors(dynamo, 'Products', 'by-embedding', vector=[0.1, 0.2], top_k=5)
    assert len(results) == 2
    assert recorded['TableName'] == 'Products'


# --- numpy-absent import guard ----------------------------------------------


def test_module_does_not_import_numpy():
    # Run in a fresh interpreter so a numpy pre-imported by the test env
    # (e.g. via another test) cannot mask a stray import in the module.
    # Use the current interpreter (sys.executable) directly — invoking a package
    # manager here would trigger dependency resolution and is not hermetic.
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            "import prismarine.runtime.dynamo_vectors, sys; assert 'numpy' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
