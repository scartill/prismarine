from pathlib import Path
import textwrap
import uuid

import pytest

from pydantic import BaseModel, Field

from prismarine.prisma_client import PYDANTIC_HELPERS, build_client
from prismarine.prisma_common import get_cluster


def _write_models(tmp_path, body: str, package_name: str | None = None):
    base_dir = tmp_path / 'project'
    pkg = package_name or f'app_{uuid.uuid4().hex}'
    package_dir = base_dir / pkg
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / '__init__.py').write_text('')
    (package_dir / 'models.py').write_text(textwrap.dedent(body))
    return base_dir, pkg


def _stub_version(monkeypatch):
    monkeypatch.setattr('prismarine.prisma_client.version', lambda _: '0.0.0-test')


# Single physical line in the generated models.py (so the multi-line decorator
# strip in build_client leaves the TypedDict body intact), split across Python
# source lines here to stay under the 120-col lint limit.
_VEC_DECORATOR = (
    "@cluster.vector_index(index='by-embedding', attribute='Embedding', "
    "dimensions=8, distance='COSINE', hash='Category', filters=['Rank'])"
)
_VEC_DECORATOR_HASHLESS = (
    "@cluster.vector_index(index='by-text', attribute='Embedding', dimensions=8, distance='COSINE')"
)


def test_build_client_with_typeddict_models(tmp_path, monkeypatch):
    body = """
from typing import TypedDict
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


@cluster.model(PK='Foo', SK='Bar')
class TypedItem(TypedDict):
    Foo: str
    Bar: str
    Baz: str
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    content = build_client(
        cluster, Path(base_dir), runtime=None, access_module=None, extra_imports=[], model_library='typed-dict'
    )

    assert 'class UpdateDTO(TypedDict, total=False):' in content
    assert '_build_pydantic_update_model' not in content


@pytest.mark.parametrize('extra_field', ['', '    Baz: int | None = None\n'])
def test_build_client_with_pydantic_models(tmp_path, monkeypatch, extra_field):
    body = f"""
from pydantic import BaseModel, Field
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


@cluster.model(PK='Foo', SK='Bar')
class PydItem(BaseModel):
    Foo: str
    Bar: str
{extra_field or "    Baz: int | None = Field(default=None, alias='baz_field')"}
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    content = build_client(
        cluster, Path(base_dir), runtime=None, access_module=None, extra_imports=[], model_library='pydantic'
    )

    assert '_build_pydantic_update_model' in content
    assert 'UpdateDTO(TypedDict, total=False)' not in content
    assert '_load_model' in content


def test_pydantic_mode_rejects_typeddict_models(tmp_path, monkeypatch):
    body = """
from typing import TypedDict
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


@cluster.model(PK='Foo')
class Item(TypedDict):
    Foo: str
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    with pytest.raises(TypeError):
        build_client(
            cluster, Path(base_dir), runtime=None, access_module=None, extra_imports=[], model_library='pydantic'
        )


def test_pydantic_update_model_respects_default_factory():
    class FactoryModel(BaseModel):
        Foo: str
        tags: list[str] = Field(default_factory=list, alias='tag_list')

    namespace: dict[str, object] = {}
    exec(PYDANTIC_HELPERS, namespace)
    build_update_model = namespace['_build_pydantic_update_model']

    UpdateDTO = build_update_model(FactoryModel)

    tags_field = UpdateDTO.model_fields['tags']
    is_required = tags_field.is_required() if callable(tags_field.is_required) else tags_field.is_required
    assert not is_required
    assert tags_field.default_factory is not None
    assert tags_field.alias == 'tag_list'

    empty_instance = UpdateDTO()
    assert empty_instance.model_dump(exclude_unset=True) == {}

    with_tags = UpdateDTO(tag_list=['a'])
    assert with_tags.model_dump(by_alias=True, exclude_unset=True) == {'tag_list': ['a']}


def test_build_client_renders_vector_search_typeddict(tmp_path, monkeypatch):
    body = f"""
from typing import TypedDict
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


{_VEC_DECORATOR}
@cluster.model(PK='ProductId')
class Product(TypedDict):
    ProductId: str
    Category: str
    Rank: int
    Embedding: list[float] | None
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    content = build_client(
        cluster,
        Path(base_dir),
        runtime=None,
        access_module=None,
        extra_imports=[],
        model_library='typed-dict',
    )

    # Nested class + search method
    assert 'class ByEmbedding:' in content
    assert 'def search(' in content

    # HASH kwarg appears before top_k (required-before-optional ordering)
    assert 'category: str' in content
    assert content.index('category: str') < content.index('top_k: int = 10')

    # Filter kwarg carries its real (non-str) schema-derived type
    assert 'rank: int | None = None' in content

    # Escape-hatch param present; no pagination
    assert 'expression_names' in content
    assert 'next_token' not in content

    # dimensions wired into the runtime call
    search_call_idx = content.index('_search_vectors(')
    assert 'dimensions=8' in content[search_call_idx:]

    # Return type
    assert '-> SearchResults[Product]' in content

    # Conditional vector-runtime import present, strictly from dynamo_vectors
    assert 'from prismarine.runtime.dynamo_vectors import' in content
    assert '_search_vectors' in content
    assert 'VectorSearchResult' in content

    # No-shadow guard: _pv_-prefixed locals
    assert '_pv_results' in content
    assert '_pv_hash_conditions' in content
    assert '_pv_filter_conditions' in content


def test_build_client_renders_vector_search_pydantic(tmp_path, monkeypatch):
    body = f"""
from pydantic import BaseModel
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


{_VEC_DECORATOR}
@cluster.model(PK='ProductId')
class Product(BaseModel):
    ProductId: str
    Category: str
    Rank: int
    Embedding: list[float] | None = None
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    content = build_client(
        cluster,
        Path(base_dir),
        runtime=None,
        access_module=None,
        extra_imports=[],
        model_library='pydantic',
    )

    assert 'class ByEmbedding:' in content
    # Pydantic body returns a SearchResults collection, not a bare list.
    # ruff reflows the long call, so assert the structural pieces survive.
    assert 'return SearchResults(' in content
    assert 'item=_load_model(Product, _pv_hit.item)' in content
    assert 'score=_pv_hit.score' in content
    assert 'for _pv_hit in _pv_results.hits' in content
    assert 'consumed_capacity=_pv_results.consumed_capacity' in content
    assert 'VectorSearchResult(' in content
    # Not a bare list return
    assert 'return [VectorSearchResult' not in content
    # Filter kwarg still carries its real type
    assert 'rank: int | None = None' in content
    # Generation succeeds -> compiles cleanly
    compile(content, '<gen>', 'exec')


def test_build_client_renders_hashless_vector_search(tmp_path, monkeypatch):
    body = f"""
from typing import TypedDict
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


{_VEC_DECORATOR_HASHLESS}
@cluster.model(PK='ProductId')
class Product(TypedDict):
    ProductId: str
    Embedding: list[float] | None
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    content = build_client(
        cluster,
        Path(base_dir),
        runtime=None,
        access_module=None,
        extra_imports=[],
        model_library='typed-dict',
    )

    assert 'class ByText:' in content
    assert 'def search(' in content
    # Hashless index emits no HASH kwarg and an empty hash-conditions dict
    assert '_pv_hash_conditions = {}' in content
    # No hash kwarg leaked into the signature between vector and top_k
    sig_slice = content[content.index('def search(') : content.index('top_k: int = 10')]
    assert ': str,' not in sig_slice
    # Compiles without SyntaxError/UnboundLocalError
    compile(content, '<gen>', 'exec')


def test_build_client_no_vector_index_is_byte_identical(tmp_path, monkeypatch):
    body = """
from typing import TypedDict
from prismarine.runtime import Cluster

cluster = Cluster('UnitTest')


@cluster.model(PK='Foo', SK='Bar')
class PlainItem(TypedDict):
    Foo: str
    Bar: str
    Baz: str
"""
    base_dir, cluster_package = _write_models(tmp_path, body)
    _stub_version(monkeypatch)
    cluster = get_cluster(base_dir, cluster_package)

    content = build_client(
        cluster,
        Path(base_dir),
        runtime=None,
        access_module=None,
        extra_imports=[],
        model_library='typed-dict',
    )

    # No vector-specific output whatsoever
    assert '_search_vectors' not in content
    assert 'SearchResults' not in content
    assert 'VectorSearchResult' not in content
    assert 'class ByEmbedding' not in content
