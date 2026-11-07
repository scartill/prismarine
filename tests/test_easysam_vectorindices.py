from prismarine.prisma_easysam import build_dynamo_tables
from prismarine.runtime.cluster import Cluster


def test_vectorindices_full_shape():
    c = Cluster()

    @c.vector_index(
        index='by-embedding',
        attribute='Embedding',
        dimensions=1536,
        distance='COSINE',
        hash='Category',
        filters=['Brand'],
    )
    @c.model(PK='ProductId')
    class Product:
        pass

    result = build_dynamo_tables('', c)

    vector_indices = result['Product']['vectorindices']
    assert vector_indices == [
        {
            'name': 'by-embedding',
            'attribute': 'Embedding',
            'dimensions': 1536,
            'distance': 'COSINE',
            'hash': 'Category',
            'filters': ['Brand'],
        }
    ]


def test_vectorindices_omits_hash_and_filters_when_absent():
    c = Cluster()

    @c.vector_index(
        index='by-embedding',
        attribute='Embedding',
        dimensions=8,
        distance='DOT_PRODUCT',
    )
    @c.model(PK='ProductId')
    class Product:
        pass

    result = build_dynamo_tables('', c)

    vector_indices = result['Product']['vectorindices']
    assert vector_indices == [
        {
            'name': 'by-embedding',
            'attribute': 'Embedding',
            'dimensions': 8,
            'distance': 'DOT_PRODUCT',
        }
    ]
    assert 'hash' not in vector_indices[0]
    assert 'filters' not in vector_indices[0]


def test_vector_attributes_absent_from_attribute_definitions():
    "Critique E5: vector attribute/hash/filters must not pollute AttributeDefinitions."
    c = Cluster()

    @c.vector_index(
        index='by-embedding',
        attribute='Embedding',
        dimensions=1536,
        distance='COSINE',
        hash='Category',
        filters=['Brand'],
    )
    @c.model(PK='ProductId')
    class Product:
        pass

    result = build_dynamo_tables('', c)

    attribute_names = {attr['name'] for attr in result['Product']['attributes']}

    # Only the table key schema should appear in AttributeDefinitions.
    assert attribute_names == {'ProductId'}
    assert 'Embedding' not in attribute_names
    assert 'Category' not in attribute_names
    assert 'Brand' not in attribute_names


def test_vector_attribute_still_present_when_independently_a_key():
    "E5: a name that is independently a table/GSI key legitimately stays in AttributeDefinitions."
    c = Cluster()

    @c.vector_index(
        index='by-embedding',
        attribute='Embedding',
        dimensions=8,
        distance='COSINE',
        hash='Category',
    )
    @c.index(index='by-category', PK='Category')
    @c.model(PK='ProductId')
    class Product:
        pass

    result = build_dynamo_tables('', c)

    attribute_names = {attr['name'] for attr in result['Product']['attributes']}

    # Category is a GSI key here, so it legitimately appears regardless of being a vector hash.
    assert 'Category' in attribute_names
    # Embedding is only a vector attribute, so it must not appear.
    assert 'Embedding' not in attribute_names


def test_model_without_vector_index_has_no_vectorindices_key():
    c = Cluster()

    @c.model(PK='ProductId')
    class Product:
        pass

    result = build_dynamo_tables('', c)

    assert 'vectorindices' not in result['Product']


def test_multiple_vector_indices_emitted():
    c = Cluster()

    @c.vector_index(index='by-a', attribute='EmbeddingA', dimensions=8, distance='COSINE')
    @c.vector_index(index='by-b', attribute='EmbeddingB', dimensions=16, distance='EUCLIDEAN', filters=['Brand'])
    @c.model(PK='ProductId')
    class Product:
        pass

    result = build_dynamo_tables('', c)

    vector_indices = result['Product']['vectorindices']
    by_name = {vi['name']: vi for vi in vector_indices}

    assert set(by_name) == {'by-a', 'by-b'}
    assert by_name['by-a'] == {
        'name': 'by-a',
        'attribute': 'EmbeddingA',
        'dimensions': 8,
        'distance': 'COSINE',
    }
    assert by_name['by-b'] == {
        'name': 'by-b',
        'attribute': 'EmbeddingB',
        'dimensions': 16,
        'distance': 'EUCLIDEAN',
        'filters': ['Brand'],
    }
