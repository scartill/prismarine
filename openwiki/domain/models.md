---
type: Domain Guide
title: Models and Clusters
resource: https://github.com/scartill/prismarine
openwiki:
  roles: [domain, architecture]
  change_kinds: [lifecycle, public-api]
  source_paths: [src/prismarine/runtime/cluster.py, src/prismarine/prisma_common.py]
  symbols: [Cluster, TriggerConfig, model, index]
  test_paths: [tests/test_cluster.py]
  invariants: [Models must have valid PK/SK definitions, Cluster prefix must be consistent across related models]
  validation_commands: [pytest tests/test_cluster.py -v]
---

# Models and Clusters

Models are the core abstraction in Prismarine. They define the structure of your DynamoDB data and provide the basis for all generated client code.

## Cluster Class

The `Cluster` class is the primary decorator and registry for models:

```python
from prismarine import Cluster

c = Cluster('MyAppPrefix')  # Sets table name prefix
```

**Key Properties:**
- `prefix`: Table name prefix (e.g., 'MyAppPrefix')
- `models`: List of registered models
- `exports`: Dictionary of exported classes

## Model Definition

### Basic Model

```python
from typing import TypedDict, NotRequired
from prismarine import Cluster

c = Cluster('MyApp')

@c.model(PK='user_id', SK='email')
class User(TypedDict):
    user_id: str
    email: str
    name: str
    age: NotRequired[int]  # Optional field
```

**Parameters:**
- `PK`: Partition Key (required)
- `SK`: Sort Key (optional)
- `table`: Custom table name (overrides prefix + class name)
- `name`: Custom model name
- `alias`: Alternative class name in generated client
- `trigger`: DynamoDB Stream trigger configuration
- `ttl`: Time-to-live field name

### Pydantic Model

```python
from pydantic import BaseModel
from prismarine import Cluster

c = Cluster('MyApp')

@c.model(PK='user_id', SK='email')
class User(BaseModel):
    user_id: str
    email: str
    name: str
    age: int | None = None  # Optional field
```

**Requirements:**
- Install with `pip install prismarine[pydantic]`
- Use `--model-library pydantic` when generating client

## Primary Keys and Sort Keys

### Partition Key (PK)

The partition key determines how data is distributed across DynamoDB partitions. Choose a high-cardinality field for even distribution.

```python
@c.model(PK='user_id')  # Single partition key
class User(TypedDict):
    user_id: str
    email: str
```

### Composite Key (PK + SK)

```python
@c.model(PK='user_id', SK='email')  # Composite key
class UserContact(TypedDict):
    user_id: str
    email: str
    phone: str
    preferred: bool
```

**Usage:**
- `get(foo='value1', bar='value2')` - Get by composite key
- `list(foo='value1')` - Query all items with same partition key
- `scan()` - Full table scan (use sparingly)

## Secondary Indexes

Add secondary indexes using the `@c.index()` decorator:

```python
@c.model(PK='user_id', SK='email')
class UserContact(TypedDict):
    user_id: str
    email: str
    phone: str
    preferred: bool

@c.index(index='ByPhone', PK='phone', SK='user_id')
class UserContactIndex:
    pass
```

**Index Parameters:**
- `index`: Index name (required)
- `PK`: Partition key for the index
- `SK`: Sort key for the index (optional)

**Usage:**
```python
# Query by index
UserContactModel.query_by_index_ByPhone(phone='123-456-7890')
```

## Trigger Configuration (EasySAM)

Configure DynamoDB Stream Triggers for EasySAM integration:

```python
from prismarine import TriggerConfig

trigger_config = TriggerConfig(
    function='my-lambda-function',
    viewtype='new-and-old',
    batchsize=100,
    batchwindow=5,
    startingposition='latest'
)

@c.model(PK='user_id', SK='email', trigger=trigger_config)
class User(TypedDict):
    user_id: str
    email: str
    name: str
```

**TriggerConfig Parameters:**
- `function`: Lambda function name (required)
- `viewtype`: Stream view type ['keys-only', 'new', 'old', 'new-and-old']
- `batchsize`: Number of records per batch
- `batchwindow`: Time window in seconds
- `startingposition`: 'trim-horizon' or 'latest'

## Time-to-Live (TTL)

Automatically expire items based on a timestamp field:

```python
@c.model(PK='user_id', SK='email', ttl='expiration_time')
class Session(TypedDict):
    user_id: str
    email: str
    expiration_time: int  # Unix timestamp
```

**TTL Requirements:**
- Field must be an integer (Unix timestamp)
- DynamoDB TTL must be enabled on the table
- Field name is used for both storage and TTL configuration

## Custom Table Names

Override the default table naming convention:

```python
@c.model(PK='user_id', table='CustomTableName')
class User(TypedDict):
    user_id: str
    email: str
```

**Naming Convention:**
- Default: `{prefix}{class_name}` (e.g., 'MyAppUser')
- Custom: Explicitly set via `table` parameter

## Model Aliases

Use a different class name in the generated client:

```python
@c.model(PK='user_id', SK='email', alias='UserModel')
class User(TypedDict):
    user_id: str
    email: str
```

**Result:** Generated class will be `UserModel` instead of `User`

## Multiple Models in One Cluster

```python
c = Cluster('MyApp')

@c.model(PK='user_id', SK='email')
class User(TypedDict):
    user_id: str
    email: str
    name: str

@c.model(PK='product_id', SK='category')
class Product(TypedDict):
    product_id: str
    category: str
    price: float

@c.model(PK='order_id', SK='user_id')
class Order(TypedDict):
    order_id: str
    user_id: str
    total: float
```

**Benefits:**
- Related models share the same table prefix
- Can be generated with a single command
- Consistent naming conventions

## Model Metadata

Each registered model includes:

```python
{
    'cls': User,                    # Original class
    'main': {'PK': 'user_id', 'SK': 'email'},  # PK/SK definition
    'table': 'MyAppUser',           # Table name
    'indexes': {},                  # Secondary indexes
    'class_name': 'User',           # Class name
    'name': None,                   # Custom name if provided
    'trigger': None,                # Trigger config if provided
    'ttl': None                     # TTL field if provided
}
```

## Best Practices

### 1. Naming Conventions

- Use PascalCase for model class names
- Use snake_case for field names
- Keep PK/SK names descriptive and consistent

### 2. Partition Key Design

- Choose high-cardinality fields for PK
- Avoid hot partitions with low-cardinality PK
- Consider access patterns when designing PK/SK

### 3. Optional Fields

- Use `NotRequired` for optional fields in TypedDict
- Use `Optional[Type]` or `Type | None` for Pydantic models
- Document which fields are required vs optional

### 4. Index Design

- Create indexes for common query patterns
- Consider GSI vs LSI based on access patterns
- Document index usage in model comments

### 5. TTL Strategy

- Set appropriate expiration times
- Monitor TTL metrics in DynamoDB
- Consider using TTL for temporary data

## Change Navigation

- **When to consult this page**: When defining new models, modifying existing models, or troubleshooting model registration issues
- **Runtime invariants**:
  - Models must have valid PK/SK definitions
  - Cluster prefix must be consistent across related models
  - Generated client must import models correctly
- **Extension points**:
  - Custom table names
  - Model aliases
  - Additional decorator parameters
  - New index types
- **Source files**:
  - `src/prismarine/runtime/cluster.py` (core Cluster class)
  - `src/prismarine/prisma_common.py` (model discovery utilities)
- **Focused tests**:
  - `tests/test_cluster.py` (model registration and validation)
  - `tests/test_models.py` (model behavior)
- **Validation**:
  - `pytest tests/test_cluster.py -v` (run model tests)
  - Check generated client includes your models

## Common Patterns

### User Profile Example

```python
from typing import TypedDict, NotRequired
from prismarine import Cluster

c = Cluster('SocialApp')

@c.model(PK='user_id', SK='profile')
class UserProfile(TypedDict):
    user_id: str
    username: str
    display_name: str
    bio: NotRequired[str]
    avatar_url: NotRequired[str]
    created_at: str

@c.model(PK='user_id', SK='settings')
class UserSettings(TypedDict):
    user_id: str
    theme: str
    notifications_enabled: bool
    privacy_level: int
```

### E-commerce Example

```python
from typing import TypedDict, NotRequired
from prismarine import Cluster

c = Cluster('EcommerceApp')

@c.model(PK='product_id', SK='details')
class Product(TypedDict):
    product_id: str
    name: str
    description: str
    price: float
    category: str
    stock: int

@c.model(PK='user_id', SK='cart')
class ShoppingCart(TypedDict):
    user_id: str
    product_id: str
    quantity: int
    added_at: str

@c.index(index='ByCategory', PK='category', SK='product_id')
class ProductCategoryIndex:
    pass

@c.index(index='ByPrice', PK='price_range', SK='product_id')
class ProductPriceIndex:
    pass
```

### Session Management Example

```python
from typing import TypedDict
from prismarine import Cluster, TriggerConfig

c = Cluster('AuthService')

@c.model(
    PK='user_id', 
    SK='session',
    ttl='expires_at',
    trigger=TriggerConfig(
        function='auth-stream-processor',
        viewtype='new-and-old',
        batchsize=50
    )
)
class UserSession(TypedDict):
    user_id: str
    session_id: str
    expires_at: int  # Unix timestamp
    ip_address: str
    user_agent: str
```

## Troubleshooting

### Model Not Found

**Problem**: Model not appearing in generated client

**Solution**:
1. Verify decorator is `@c.model()` not just `@model()`
2. Check that cluster instance `c` is the same one used for all models
3. Ensure models are in a discoverable Python package
4. Verify no import errors in model definition file

### Invalid PK/SK

**Problem**: Generation fails with PK/SK errors

**Solution**:
1. Ensure PK is always provided
2. Check that SK is provided when needed
3. Verify field names exist in the model
4. Ensure fields are hashable types

### Table Name Conflicts

**Problem**: Multiple models using same table

**Solution**:
1. Use different SK values for composite keys
2. Set custom `table` parameter for conflicting models
3. Consider separate clusters for unrelated models

### Import Errors in Generated Client

**Problem**: Generated client has import errors

**Solution**:
1. Verify all model dependencies are importable
2. Check that extra imports are correctly specified
3. Ensure model library (TypedDict vs Pydantic) matches generation command