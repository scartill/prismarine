from typing import TypedDict, NotRequired
from prismarine.runtime import Cluster


c = Cluster('MyDatabase')


@c.model(PK='Foo', SK='Bar')
class Item(TypedDict):
    Foo: str
    Bar: str
    Baz: NotRequired[str]


@c.vector_index(index='by-embedding', attribute='Embedding', dimensions=1536, distance='COSINE', hash='Category', filters=['Brand'])
@c.model(PK='ProductId')
class Product(TypedDict):
    ProductId: str
    Category: str
    Brand: str
    Embedding: list[float] | None
