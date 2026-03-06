# Prismarine - DynamoDB ORM

Prismarine is a Pythonic ORM for DynamoDB, designed to simplify interactions with DynamoDB by providing a structured and Python-friendly interface. It leverages Python's type hinting and decorators to define models, which are then used to generate client code for database operations.

Key features include:
- **Model Definition**: Models are defined using Python's `TypedDict` (default) or, optionally, `pydantic.BaseModel` classes and are decorated with the `Cluster.model` decorator to specify primary and sort keys.
- **Automatic Client Generation**: The `prismarine_client.py` file is auto-generated, containing classes and methods for interacting with DynamoDB tables based on the defined models.
- **Easy Integration**: The generated client code integrates seamlessly with existing Python applications, providing methods for common database operations.

Prismarine aims to streamline the development process by reducing boilerplate code and ensuring that database interactions are type-safe and maintainable.

Prismarine works best with [EasySAM](https://github.com/scartill/easysam).

## Installation

```bash
pip install prismarine
```

## Quick Overview

### Expected Directory Structure:

```
<base-path>/
  <package-name>/
    - models.py
    - db.py
    - prismarine_client.py // Auto-generated
```

Models are defined in the `models.py` file. Each model is a `TypedDict`, decorated with the `Cluster.model` decorator. You can also opt into Pydantic models (see [Using Pydantic Models](#using-pydantic-models)).

The `Cluster` class is used to group extension models together. It also sets a prefix for the table names.

```python
from typing import TypedDict, NotRequired
from prismarine import Cluster

c = Cluster('TapgameExample')

@c.model(PK='Foo', SK='Bar')
class Team(TypedDict):
    Foo: str
    Bar: str
    Baz: NotRequired[str]
```

If we place this code in `<base-path>/<package-name>/models.py` and the following command is run, it will generate a `prismarine_client.py` file in the same directory:

```bash
prismarine generate-client --base <base-path> <package-name>
```

The `prismarine_client.py` file will contain the following code:

```python
class TeamModel(Model):
    table_name = 'TapgameExampleTeam'
    PK = 'Foo'
    SK = 'Bar'

    class UpdateDTO(TypedDict, total=False):
        Foo: str
        Bar: str
        Baz: NotRequired[str]

    @staticmethod
    def list(*, foo: str) -> List[Team]:
        ...

    @staticmethod
    def get(*, bar: str, foo: str, default: Team | EllipsisType = ...) -> Team:
        ...

    @staticmethod
    def put(team: Team) -> Team:
        ...

    @staticmethod
    def update(
        team: UpdateDTO, *, foo: str, bar: str, default: Team | EllipsisType = ...
    ) -> Team:
        ...

    @staticmethod
    def save(updated: Team, *, original: Team | None = None) -> Team:
        ...

    @staticmethod
    def delete(*, bar: str, foo: str):
        ...

    @staticmethod
    def scan() -> List[Team]:
        ...
```

As you can see, the `TeamModel` class has static methods for all the CRUD operations. The `UpdateDTO` class is similar to the `Team` class, but all fields are optional.

### Creating a `db.py` File

Now, let's create a `db.py` file in the same directory:

```python
import example.prismarine_client as pc

class TeamModel(pc.TeamModel):
    pass
```

Although you can import and use `prismarine_client.py` directly, it is recommended to create a `db.py` file that imports the generated client and extends it with your own methods.

You can now use the `TeamModel` class in your code:

```python
from sam.common.example.db import TeamModel
from sam.common.prismarine import DbNotFound

# Create a new team
new_team = TeamModel.put({'Foo': 'foo', 'Bar': 'bar', 'Baz': 'baz'})

# List teams by a primary key
teams_by_foo = TeamModel.list(foo='foo')

# Get a team
try:
    team = TeamModel.get(foo='foo', bar='bar')
except DbNotFound:
    print('Team not found')

# Update a team
updated_team = TeamModel.update(
    {'Baz': 'new_baz'},
    foo='foo',
    bar='bar'
)

# List all teams
all_teams = TeamModel.scan()

# Delete a team
TeamModel.delete(foo='foo', bar='bar')
```

You may notice that Prismarine mostly requires named arguments. This ensures that changes to field names do not cause silent code failures. For example, if the Sort Key name is changed, all usages of `get` and `update` methods will break and be highlighted by the IDE and linter. This approach also makes the code more readable.

### Using Pydantic Models

Prismarine can optionally generate clients that work with `pydantic.BaseModel` schemas rather than `TypedDict`.

1. Install the optional dependency:

```bash
pip install "prismarine[pydantic]"
```

2. Define your models as `BaseModel` subclasses in `models.py`.
3. Run the generator with the Pydantic model library enabled:

```bash
prismarine generate-client --model-library pydantic --base <base-path> <package-name>
```

With this flag disabled (the default `typed-dict` mode), Prismarine behaves exactly as before. The Pydantic mode keeps the same API surface but returns/accepts BaseModel instances and automatically converts data during CRUD operations.

## Advanced Usage

### `model` Decorator

The `Cluster.model` decorator accepts several arguments to customize the model:

- **`PK`** (required): The name of the partition key attribute
- **`SK`** (optional): The name of the sort key attribute
- **`table`** (optional): Sets a full custom table name (without prefix)
- **`name`** (optional): Sets a custom model name (used with prefix)
- **`trigger`** (optional): Configures a DynamoDB stream trigger for the table (when using with EasySAM)
- **`ttl`** (optional): Configures a DynamoDB Time To Live (TTL) attribute for the table (when using with EasySAM)

For example, if the `Cluster` has a prefix `TapgameExample`, by default the `Team` model will have the table name `TapgameExampleTeam`. If we set `name='Custom'`, the table name will be `TapgameExampleCustom`. And if we set `table='CustomTable'`, the table name will simply be `CustomTable`, without the prefix.

#### DynamoDB Stream Triggers

When using Prismarine with [EasySAM](https://github.com/scartill/easysam), you can configure DynamoDB stream triggers directly on your models using the `trigger` parameter. This allows a Lambda function to be automatically invoked whenever items in the table are inserted, modified, or removed.

**Simple trigger (string format):**

```python
@c.model(PK='Foo', SK='Bar', trigger='itemlogger')
class Item(TypedDict):
    Foo: str
    Bar: str
```

**Advanced form** (with options):

```python
@c.model(
    PK='Foo',
    SK='Bar',
    trigger={
        'function': 'my-lambda',
        'viewtype': 'new-and-old',  # Optional: keys-only, new, old, new-and-old (default: new-and-old)
        'batchsize': 10,             # Optional: number of records per batch
        'batchwindow': 5,            # Optional: seconds to wait for batch
        'startingposition': 'latest' # Optional: trim-horizon, latest (default: latest)
    }
)
class Item(TypedDict):
    Foo: str
    Bar: str
```

The trigger configuration options:
- **function**: The name of the Lambda function to trigger
- **viewtype**: What data to include in the stream record (default: `new-and-old`)
  - `keys-only`: Only the keys of the modified item
  - `new`: Only the new item image
  - `old`: Only the old item image
  - `new-and-old`: Both old and new item images
- **batchsize**: Number of records to process per batch (improves throughput)
- **batchwindow**: Maximum number of seconds to wait for a batch (reduces latency)
- **startingposition**: Where to start reading the stream (default: `latest`)
  - `trim-horizon`: Start from the oldest record available
  - `latest`: Start from the most recent record

When EasySAM generates the CloudFormation template, it will automatically:
- Enable DynamoDB Streams on the table
- Create an EventSourceMapping to connect the stream to your Lambda function
- Configure the appropriate IAM permissions for stream access

The trigger Lambda function will receive DynamoDB stream events with information about inserted, modified, or removed items.

#### DynamoDB Time To Live (TTL)

When using Prismarine with [EasySAM](https://github.com/scartill/easysam), you can configure DynamoDB Time To Live (TTL) directly on your models using the `ttl` parameter. This allows DynamoDB to automatically delete items after a specified expiration time.

**Example:**

```python
from typing import TypedDict, NotRequired
from prismarine.runtime import Cluster

c = Cluster('PrismaTTL')

@c.model(PK='Foo', SK='Bar', ttl='ExpireAt')
class Item(TypedDict):
    Foo: str
    Bar: str
    Baz: NotRequired[str]
    ExpireAt: int  # Unix timestamp (seconds since epoch)
```

The `ttl` parameter specifies the attribute name that will store the expiration timestamp. When you create or update an item, set this attribute to a Unix timestamp (number of seconds since epoch). DynamoDB will automatically delete items within 48 hours after the TTL timestamp has passed.

**Benefits:**
- **Automatic Cleanup**: Items are automatically deleted without additional code
- **Cost Effective**: TTL deletion is free and doesn't consume write capacity units
- **Declarative**: Define TTL directly in your model configuration

When EasySAM generates the CloudFormation template, it will automatically:
- Enable TTL on the DynamoDB table
- Configure the `TimeToLiveSpecification` with the specified attribute name

### `index` Decorator

`index` decorators must be used *before* the `model` decorator.

The `Cluster.index` decorator is used to define a secondary index. It accepts `PK`, `SK`, and `index` arguments.

```python
@c.index(index='by-bar', PK='Bar', SK='Foo')
@c.model(PK='Foo', SK='Bar')
class Team(TypedDict):
    Foo: str
    Bar: str
    Baz: NotRequired[str]
```

This will add a subclass `ByBar` to the `TeamModel` class:

```python
class TeamModel(Model):
    ...

    class ByBar:
        PK = 'Bar'
        SK = 'Foo'

        @staticmethod
        def list(
            *,
            bar: str,
            limit: int | None = None,
            direction: Literal['ASC', 'DESC'] = 'ASC'
        ) -> List[Team]:
            ...

        @staticmethod
        def get(*, bar: str, foo: str) -> Team:
            ...
```

### `export` Decorator

The `Cluster.export` decorator is used to define a class that is not a model, but is exported from the cluster. It accepts a class as an argument. It is required to used on all classes that serve as types for model elements.

```python
@c.export
class Team(TypedDict):
    Foo: str
    Bar: str
```

## Other Commands

### `version`

Prints the version of Prismarine.

```bash
prismarine version
```
