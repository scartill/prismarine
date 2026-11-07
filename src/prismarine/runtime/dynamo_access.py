import boto3

from types_boto3_dynamodb import DynamoDBClient, ServiceResource
from types_boto3_dynamodb.service_resource import Table


class DynamoAccess:
    def get_resource(self) -> ServiceResource: ...
    def get_table(self, full_model_name: str) -> Table: ...

    def get_client(self) -> DynamoDBClient:
        # Return a standalone low-level client, NOT resource.meta.client.
        # The resource's client carries boto3's high-level DynamoDB parameter
        # customization (copy_dynamodb_params), which runs request params through
        # the Decimal/number transform. For the low-level SearchVectors call that
        # transform corrupts the already-serialized {"N": "..."} SearchVector and
        # DynamoDB rejects it ("must be a 32-bit floating-point number"). A plain
        # client has no such handler. Derive region/credentials from the resource
        # so custom-access subclasses keep working unchanged.
        resource = self.get_resource()
        return boto3.client('dynamodb', region_name=resource.meta.client.meta.region_name)
