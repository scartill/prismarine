import pytest

from prismarine.runtime.cluster import Cluster


def test_vector_index_registers_expected_dict():
    c = Cluster()

    @c.vector_index(
        index='by-embedding',
        attribute='Embedding',
        dimensions=1536,
        distance='COSINE',
        hash='Category',
        filters=['Brand'],
    )
    @c.model(PK='PK', SK='SK')
    class Product:
        pass

    model = c.models[0]
    assert model['vector_indexes']['by-embedding'] == {
        'attribute': 'Embedding',
        'dimensions': 1536,
        'distance': 'COSINE',
        'hash': 'Category',
        'filters': ['Brand'],
    }


def test_model_without_vector_index_has_empty_dict():
    c = Cluster()

    @c.model(PK='PK', SK='SK')
    class Product:
        pass

    assert c.models[0]['vector_indexes'] == {}


def test_invalid_distance_raises():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='MANHATTAN')
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


@pytest.mark.parametrize('dimensions', [0, 5000])
def test_invalid_dimensions_raises(dimensions):
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=dimensions, distance='COSINE')
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_reserved_hash_name_raises():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', hash='Vector')
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_reserved_filter_name_raises():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', filters=['TopK'])
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_non_colliding_hash_does_not_raise():
    c = Cluster()

    @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', hash='Category')
    @c.model(PK='PK', SK='SK')
    class Product:
        pass

    assert 'by-embedding' in c.models[0]['vector_indexes']


def test_hash_filter_collision_raises():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(
            index='by-embedding',
            attribute='Embedding',
            dimensions=8,
            distance='COSINE',
            hash='Category',
            filters=['category'],
        )
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_duplicate_filters_raise():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(
            index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', filters=['Brand', 'brand']
        )
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_internal_local_hash_name_raises():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', hash='Results')
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_internal_local_filter_name_raises():
    c = Cluster()

    with pytest.raises(ValueError):

        @c.vector_index(
            index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', filters=['hash_conditions']
        )
        @c.model(PK='PK', SK='SK')
        class Product:
            pass


def test_sixth_vector_index_raises():
    c = Cluster()

    @c.model(PK='PK', SK='SK')
    class Product:
        pass

    for n in range(5):
        c.vector_index(index=f'by-embedding-{n}', attribute=f'Embedding{n}', dimensions=8, distance='COSINE')(Product)

    with pytest.raises(ValueError):
        c.vector_index(index='by-embedding-5', attribute='Embedding5', dimensions=8, distance='COSINE')(Product)


def test_hashless_vector_index_registers():
    c = Cluster()

    @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE')
    @c.model(PK='PK', SK='SK')
    class Product:
        pass

    assert c.models[0]['vector_indexes']['by-embedding'] == {
        'attribute': 'Embedding',
        'dimensions': 8,
        'distance': 'COSINE',
        'hash': None,
        'filters': [],
    }


def test_vector_index_without_model_raises():
    c = Cluster()

    with pytest.raises(Exception):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE')
        class Product:
            pass


def test_filter_named_dynamo_is_rejected():
    # 'dynamo' is the module-level client handle in the generated client;
    # a filter named Dynamo would shadow it. (Code review MEDIUM)
    import pytest

    c = Cluster()
    with pytest.raises(ValueError):

        @c.vector_index(
            index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', filters=['Dynamo']
        )
        @c.model(PK='PK')
        class Product:
            pass


def test_python_keyword_attribute_is_rejected():
    # A hash/filter normalizing to a Python keyword would emit invalid syntax. (Code review MEDIUM)
    import pytest

    c = Cluster()
    with pytest.raises(ValueError):

        @c.vector_index(index='by-embedding', attribute='Embedding', dimensions=8, distance='COSINE', hash='class')
        @c.model(PK='PK')
        class Product:
            pass
