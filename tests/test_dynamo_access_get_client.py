from types import SimpleNamespace

from prismarine.runtime.dynamo_access import DynamoAccess


def test_get_client_returns_resource_meta_client():
    sentinel = object()

    class StubAccess(DynamoAccess):
        def get_resource(self):
            return SimpleNamespace(meta=SimpleNamespace(client=sentinel))

    assert StubAccess().get_client() is sentinel


def test_subclass_overriding_only_get_resource_inherits_get_client():
    sentinel = object()

    class CustomAccess(DynamoAccess):
        # Simulates a custom-access class that only overrides get_resource;
        # get_client is inherited from the base and should still work.
        def get_resource(self):
            return SimpleNamespace(meta=SimpleNamespace(client=sentinel))

    access = CustomAccess()
    assert 'get_client' not in vars(CustomAccess)
    assert access.get_client() is sentinel
