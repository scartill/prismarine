from types_boto3_dynamodb import DynamoDBClient, ServiceResource
from types_boto3_dynamodb.service_resource import Table


class DynamoAccess:
    def get_resource(self) -> ServiceResource: ...
    def get_table(self, full_model_name: str) -> Table: ...

    def get_client(self) -> DynamoDBClient:
        return self.get_resource().meta.client
