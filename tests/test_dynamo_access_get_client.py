from types import SimpleNamespace

import boto3

from prismarine.runtime.dynamo_access import DynamoAccess


def _stub_resource(region='us-east-1'):
    # Mimic the shape get_client() reads: resource.meta.client.meta.region_name.
    return SimpleNamespace(meta=SimpleNamespace(client=SimpleNamespace(meta=SimpleNamespace(region_name=region))))


def test_get_client_returns_standalone_low_level_client():
    # get_client() must NOT return resource.meta.client: that client carries
    # boto3's high-level copy_dynamodb_params handler, which corrupts the
    # low-level SearchVectors SearchVector. It must return a fresh low-level
    # dynamodb client instead.
    class StubAccess(DynamoAccess):
        def get_resource(self):
            return _stub_resource('us-west-2')

    client = StubAccess().get_client()
    # A real low-level dynamodb client exposes search_vectors / put_item and
    # the expected service/region.
    assert client.meta.service_model.service_name == 'dynamodb'
    assert client.meta.region_name == 'us-west-2'
    # It must not be the resource's client, and must not carry the high-level
    # dynamodb param-copy customization.
    handlers = client.meta.events._emitter._handlers.prefix_search('provide-client-params.dynamodb')
    assert not any('copy_dynamodb_params' in str(h) for h in handlers)


def test_subclass_overriding_only_get_resource_inherits_get_client():
    # A custom-access class that only overrides get_resource still inherits a
    # working get_client().
    class CustomAccess(DynamoAccess):
        def get_resource(self):
            return _stub_resource('eu-central-1')

    access = CustomAccess()
    assert 'get_client' not in vars(CustomAccess)
    client = access.get_client()
    assert client.meta.region_name == 'eu-central-1'
    assert hasattr(client, 'put_item')


def test_resource_client_carries_copy_params_handler():
    # Guard/regression: documents WHY get_client avoids resource.meta.client.
    # The resource's underlying client registers copy_dynamodb_params, the
    # high-level transform that breaks the low-level SearchVectors call.
    resource = boto3.resource('dynamodb', region_name='us-east-1')
    handlers = resource.meta.client.meta.events._emitter._handlers.prefix_search('provide-client-params.dynamodb')
    assert any('copy_dynamodb_params' in str(h) for h in handlers)
