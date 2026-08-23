from decimal import Decimal
from typing import Any, Literal, TypeVar
import uuid
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from prismarine.runtime.dynamo_access import DynamoAccess


# Main point for now is to remove any Decimals from the data
# since they are not JSON serializable and dont work with timedelta
def prepare_item(val: Any):
    if isinstance(val, list):
        return [prepare_item(v) for v in val]
    elif isinstance(val, dict):
        return {k: prepare_item(v) for k, v in val.items()}
    elif isinstance(val, Decimal):
        if val % 1 == 0:
            return int(val)
        else:
            return float(val)

    return val


def serialize_item(val: Any):
    if isinstance(val, list):
        return [serialize_item(v) for v in val]
    elif isinstance(val, dict):
        return {k: serialize_item(v) for k, v in val.items()}
    elif isinstance(val, int) and val is not True and val is not False:
        return Decimal(val)
    elif isinstance(val, float):
        return Decimal(str(val))

    return val


def _query(
    dynamo: DynamoAccess,
    table: str,
    kv: dict[str, str | int],
    index: str = '',
    limit: int | None = None,
    direction: Literal['ASC'] | Literal['DESC'] = 'ASC',
    **kwargs
) -> list[Any]:
    if len(kv) < 1 or len(kv) > 2:
        raise Exception(f'Invalid query params {kv}')

    keys = list(kv.keys())

    condition = Key(keys[0]).eq(kv[keys[0]])
    if len(kv) == 2:
        condition = condition & Key(keys[1]).eq(kv[keys[1]])

    query_args: dict[str, Any] = {'KeyConditionExpression': condition}
    if index:
        query_args['IndexName'] = index

    if limit:
        query_args['Limit'] = limit

    if direction == 'DESC':
        query_args['ScanIndexForward'] = False

    query_args.update(kwargs)

    return prepare_item(dynamo.get_table(table).query(**query_args).get('Items', []))  # type: ignore


def _get_item(
    dynamo: DynamoAccess,
    table: str,
    kv: dict[str, str | int],
    default: Any = ...,
    **kwargs
) -> Any | None:
    return prepare_item(
        dynamo.get_table(table)
        .get_item(Key=kv, **kwargs)
        .get('Item', default if default is not ... else None)
    )


def _put_item(
    dynamo: DynamoAccess,
    table: str,
    item: Any,
    **kwargs
):
    try:
        dynamo.get_table(table).put_item(Item=serialize_item(item), **kwargs)  # type: ignore
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise DbConditionFailed(str(e)) from e
        raise


SaveItem = TypeVar('SaveItem', bound=Any)


def _save(
    dynamo: DynamoAccess,
    table: str,
    *,
    kv: dict[str, str | int],
    updated: SaveItem,
    original: SaveItem | None = None,
    **kwargs
):
    if not original:
        original = _get_item(dynamo, table, kv, **kwargs)

    if not original:
        _put_item(dynamo, table, updated)
        return

    diff = {
        key: updated[key] for key in updated.keys() if updated[key] != original[key]
    }
    if len(diff) == 0:
        return

    _update(dynamo, table, kv, diff)


def _update(
    dynamo: DynamoAccess,
    table: str,
    kv: dict[str, str | int],
    item: Any,
    **kwargs
):
    vals = {}
    keys = {}
    expressions = []
    for k, v in item.items():
        vals[f':{k}'] = serialize_item(v)
        keys[f'#{k}'] = k
        expressions.append(f'#{k} = :{k}')

    update_expression = 'SET ' + ', '.join(expressions)

    dynamo.get_table(table).update_item(
        Key=kv,
        UpdateExpression=update_expression,
        ExpressionAttributeNames=keys,
        ExpressionAttributeValues=vals,
        **kwargs
    )


def _delete(
    dynamo: DynamoAccess,
    table: str,
    kv: dict[str, str | int],
    **kwargs
):
    dynamo.get_table(table).delete_item(Key=kv, **kwargs)


def _scan(
    dynamo: DynamoAccess,
    table_name: str,
    **kwargs
) -> list[Any]:
    items = []
    last_evaluated_key = None
    table = dynamo.get_table(table_name)

    while True:
        if last_evaluated_key:
            response = table.scan(ExclusiveStartKey=last_evaluated_key, **kwargs)
        else:
            response = table.scan(**kwargs)

        items.extend(response['Items'])
        last_evaluated_key = response.get('LastEvaluatedKey')

        if not last_evaluated_key:
            break

    return prepare_item(items)  # type: ignore


class Model:
    @staticmethod
    def make_id() -> str:
        return str(uuid.uuid4())


def without(d, keys: list[str]):
    return {k: v for k, v in d.items() if k not in keys}


class DbException(Exception):
    pass


class DbNotFound(DbException):
    pass


class DbConditionFailed(DbException):
    pass
