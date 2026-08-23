---
type: Domain Guide
title: Pydantic Model Support
resource: https://github.com/scartill/prismarine
openwiki:
  roles: [domain, architecture]
  change_kinds: [lifecycle, public-api, configuration]
  source_paths: [src/prismarine/prisma_client.py, pyproject.toml]
  symbols: [model_library, BaseModel, _build_pydantic_update_model]
  test_paths: [tests/test_pydantic.py]
  invariants: [Pydantic models must be valid BaseModel subclasses, Generated UpdateDTO must match model fields]
  validation_commands: [pytest tests/test_pydantic.py -v, prismarine generate-client --model-library pydantic --help]
---

# Pydantic Model Support

Prismarine supports both Python's built-in `TypedDict` and `pydantic.BaseModel` for model definitions. Pydantic provides additional validation, serialization, and type coercion capabilities.

## Installation

To use Pydantic models, install with the pydantic extra:

```bash
pip install prismarine[pydantic]
```

Or add to your project:

```bash
pip install pydantic
```

## Model Definition

### Basic Pydantic Model

```python
from pydantic import BaseModel, Field
from prismarine import Cluster

c = Cluster('MyApp')

@c.model(PK='user_id', SK='email')
class User(BaseModel):
    user_id: str
    email: str
    name: str
    age: int | None = None  # Optional field
```

### Field Validation

```python
from pydantic import BaseModel, Field, EmailStr, field_validator
from prismarine import Cluster
from datetime import datetime

c = Cluster('MyApp')

@c.model(PK='user_id', SK='email')
class User(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=50)
    email: EmailStr  # Validates email format
    name: str = Field(..., min_length=2, max_length=100)
    age: int | None = Field(None, ge=0, le=150)
    created_at: datetime = Field(default_factory=datetime.now)
    
    @field_validator('email')
    @classmethod
    def validate_email_domain(cls, v):
        if not v.endswith('@mycompany.com'):
            raise ValueError('Only company email addresses allowed')
        return v
```

## Differences from TypedDict

| Feature | TypedDict | Pydantic |
|---------|-----------|----------|
| Validation | No | Yes |
| Default values | Limited | Full support |
| Type coercion | No | Yes |
| Serialization | Basic | Advanced |
| Field aliases | No | Yes |
| Custom validators | No | Yes |
| Performance | Faster | Slightly slower |

## Generation Command

Use the `--model-library pydantic` option:

```bash
prismarine generate-client --base . --model-library pydantic mypackage
```

## Generated Client Differences

### Pydantic Model Structure

```python
class UserModel(Model):
    table_name = 'MyAppUser'
    PK = 'user_id'
    SK = 'email'
    
    class UpdateDTO(BaseModel):
        user_id: str | None = None
        email: str | None = None
        name: str | None = None
        age: int | None = None
        created_at: datetime | None = None
    
    @staticmethod
    def put(user: User) -> User: ...
    
    @staticmethod
    def update(
        user: UpdateDTO, 
        *, 
        user_id: str, 
        email: str
    ) -> User: ...
```

### Key Differences

1. **UpdateDTO is a BaseModel**: Instead of `TypedDict`, uses `pydantic.BaseModel`
2. **Field validation**: UpdateDTO fields inherit validation from main model
3. **Type coercion**: Values are automatically coerced to correct types
4. **Default handling**: Proper handling of default values and optional fields

## Field Types

### Basic Types

```python
from pydantic import BaseModel
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal

@c.model(PK='id')
class Item(BaseModel):
    id: UUID
    name: str
    price: Decimal
    created_at: datetime
    expires_on: date | None = None
```

### Complex Types

```python
from typing import List, Dict, Optional
from pydantic import BaseModel
from enum import Enum

class Status(str, Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    PENDING = 'pending'

@c.model(PK='user_id')
class ComplexModel(BaseModel):
    tags: List[str] = []
    metadata: Dict[str, str] = {}
    status: Status = Status.ACTIVE
    preferences: Optional[Dict[str, int]] = None
```

## Field Configuration

### Default Values

```python
from pydantic import BaseModel, Field

@c.model(PK='id')
class Product(BaseModel):
    id: str
    name: str = Field(default='Unnamed Product')
    price: float = Field(default=0.0, ge=0)
    in_stock: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
```

### Field Aliases

```python
from pydantic import BaseModel, Field

@c.model(PK='user_id')
class User(BaseModel):
    user_id: str = Field(..., alias='userId')
    email_address: str = Field(..., alias='emailAddress')
    
    class Config:
        allow_population_by_field_name = True
```

### Custom Validators

```python
from pydantic import BaseModel, field_validator

@c.model(PK='username')
class ValidatedUser(BaseModel):
    username: str
    email: str
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        return v.lower()
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v
```

## Serialization and Deserialization

### Model Export

```python
user = User(
    user_id='123',
    email='user@example.com',
    name='John Doe',
    age=30
)

# Convert to dict
data = user.model_dump()
# {'user_id': '123', 'email': 'user@example.com', 'name': 'John Doe', 'age': 30}

# Convert to JSON
json_data = user.model_dump_json()
```

### Model Import

```python
# From dict
user_data = {'user_id': '123', 'email': 'user@example.com', 'name': 'John Doe'}
user = User(**user_data)

# From JSON
import json
user_data = json.loads(json_data)
user = User(**user_data)
```

## Update DTO Generation

Prismarine automatically generates an `UpdateDTO` class for Pydantic models:

```python
class UpdateDTO(BaseModel):
    user_id: str | None = None
    email: str | None = None
    name: str | None = None
    age: int | None = None
```

**Features:**
- All fields are optional (None by default)
- Inherits validation rules from main model
- Type-safe update operations
- Supports partial updates

## Best Practices

### 1. Use Pydantic When You Need

- Data validation and type coercion
- Complex field types (UUID, Decimal, datetime)
- Custom validators
- Field aliases
- Default values and optional fields
- Serialization control

### 2. Use TypedDict When You Need

- Maximum performance
- Simplicity
- Minimal dependencies
- Basic type hints only

### 3. Model Design

```python
# Good: Clear validation needs
@c.model(PK='email')
class User(BaseModel):
    email: EmailStr  # Validated email format
    name: str = Field(..., min_length=2, max_length=100)
    age: int | None = Field(None, ge=0, le=150)

# Good: Complex types
@c.model(PK='order_id')
class Order(BaseModel):
    order_id: UUID
    items: List[OrderItem]
    total: Decimal = Field(..., gt=0)
    status: OrderStatus
```

### 4. Performance Considerations

- Pydantic adds validation overhead (~10-20% slower)
- For high-throughput applications, consider TypedDict
- Use Pydantic for input validation, TypedDict for internal operations

## Migration from TypedDict

### Step 1: Install Pydantic

```bash
pip install pydantic
```

### Step 2: Update Model Definitions

```python
# Before
from typing import TypedDict, NotRequired

@c.model(PK='user_id')
class User(TypedDict):
    user_id: str
    email: str
    name: NotRequired[str]

# After
from pydantic import BaseModel

@c.model(PK='user_id')
class User(BaseModel):
    user_id: str
    email: str
    name: str | None = None
```

### Step 3: Update Generation Command

```bash
# Before
prismarine generate-client --base . mypackage

# After
prismarine generate-client --base . --model-library pydantic mypackage
```

### Step 4: Update Usage

```python
# TypedDict usage
user: User = {'user_id': '123', 'email': 'test@example.com', 'name': 'Test'}

# Pydantic usage
user = User(user_id='123', email='test@example.com', name='Test')

# Both support similar operations but with different syntax
```

## Change Navigation

- **When to consult this page**: When choosing between TypedDict and Pydantic, defining Pydantic models, or troubleshooting validation issues
- **Runtime invariants**:
  - Pydantic models must be valid BaseModel subclasses
  - Generated UpdateDTO must match model fields
  - Validation rules must be preserved in generated client
- **Extension points**:
  - Custom field validators
  - Field aliases
  - Complex type support
  - Serialization options
- **Source files**:
  - `src/prismarine/prisma_client.py` (generation logic for Pydantic)
  - `src/prismarine/prisma_common.py` (model discovery)
- **Focused tests**:
  - `tests/test_pydantic.py` (Pydantic-specific tests)
  - `tests/test_validation.py` (validation logic)
- **Validation**:
  - `pytest tests/test_pydantic.py -v` (run Pydantic tests)
  - `prismarine generate-client --model-library pydantic --help` (CLI validation)

## Common Patterns

### User Registration with Validation

```python
from pydantic import BaseModel, Field, EmailStr, field_validator
from prismarine import Cluster

c = Cluster('AuthService')

@c.model(PK='email')
class User(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: str = Field(..., min_length=3, max_length=20)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v
```

### Product Catalog with Complex Types

```python
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import List, Dict
from enum import Enum
from datetime import datetime
from uuid import UUID

class ProductStatus(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    DISCONTINUED = 'discontinued'

@c.model(PK='product_id')
class Product(BaseModel):
    product_id: UUID = Field(default_factory=UUID)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default='')
    price: Decimal = Field(..., gt=0)
    categories: List[str] = []
    attributes: Dict[str, str] = {}
    status: ProductStatus = ProductStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @field_validator('updated_at')
    @classmethod
    def update_timestamp(cls, v, info):
        if 'updated_at' in info.data:
            return info.data['updated_at']
        return datetime.now()
```

### Configuration Management

```python
from pydantic import BaseModel, Field
from typing import Dict, Any
from enum import Enum

class Environment(str, Enum):
    DEV = 'dev'
    STAGING = 'staging'
    PRODUCTION = 'production'

@c.model(PK='config_key')
class AppConfig(BaseModel):
    config_key: str
    environment: Environment
    settings: Dict[str, Any] = {}
    enabled: bool = True
    version: str = '1.0.0'
    
    @field_validator('version')
    @classmethod
    def validate_version(cls, v):
        if not v.replace('.', '').isdigit():
            raise ValueError('Version must be semantic version format')
        return v
```

## Troubleshooting

### Validation Errors

**Problem**: Model validation fails during generation or runtime

**Solution**:
1. Check field types match expected values
2. Verify custom validators are correct
3. Ensure required fields are provided
4. Check field constraints (min_length, max_length, etc.)

### Import Errors

**Problem**: Generated client can't import Pydantic classes

**Solution**:
1. Verify `prismarine[pydantic]` is installed
2. Check that `--model-library pydantic` was used in generation
3. Ensure Pydantic is in your project dependencies
4. Verify no circular imports in model definitions

### Type Mismatch Errors

**Problem**: Type coercion not working as expected

**Solution**:
1. Check field types are compatible
2. Verify Decimal fields are handled correctly
3. Ensure datetime fields use proper format
4. Check that UUID fields are valid

### Performance Issues

**Problem**: Pydantic models are too slow

**Solution**:
1. Consider using TypedDict for performance-critical paths
2. Use Pydantic only for input validation
3. Cache validation results when possible
4. Profile your application to identify bottlenecks