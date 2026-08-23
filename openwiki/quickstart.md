---
type: Reference
title: Prismarine Quickstart
resource: https://github.com/scartill/prismarine
description: Quickstart guide for Prismarine, a Pythonic DynamoDB ORM with model definition, client generation, and CRUD operations.
openwiki:
  roles: [repository, workflow]
  change_kinds: [lifecycle, public-api, configuration]
  source_paths: [README.md, pyproject.toml, src/prismarine/cli.py, src/prismarine/prisma_client.py]
  symbols: [prismarine, Cluster, generate_client]
  test_paths: []
  invariants: [Generated client code must be importable and functional]
  validation_commands: [prismarine version]
---


# Prismarine Quickstart

Prismarine is a Pythonic ORM for DynamoDB that simplifies interactions with DynamoDB by providing a structured, Python-friendly interface. It leverages Python's type hinting and decorators to define models, which are then used to generate client code for database operations.

## What's New in 1.6.0

- **Ruff Integration**: Replaced gray-formatter with Ruff for code formatting
- **EasySAM Integration**: Better support for DynamoDB Stream Triggers with EasySAM
- **Pydantic Support**: Optional Pydantic model support via `--model-library pydantic`
- **Enhanced CLI**: Additional options for DynamoDB access modules and extra imports

## Quick Task Routing

| Change Area / Intent | Relevant Wiki Page | Source Entry Points | Important Symbols | Focused Tests | Minimal Validation |
|----------------------|-------------------|---------------------|-------------------|---------------|-------------------|
| Add a new model | [Domain: Models](./domain/models.md) | `src/prismarine/runtime/cluster.py` | `Cluster.model()`, `Cluster.index()` | `tests/test_cluster.py` | `pytest tests/test_cluster.py` |
| Generate client code | [Workflows: Client Generation](./workflows/client-generation.md) | `src/prismarine/prisma_client.py`, `src/prismarine/cli.py` | `generate_client()`, `prismarine generate-client` | `tests/test_generate_client.py` | `prismarine generate-client --help` |
| Use Pydantic models | [Domain: Pydantic Support](./domain/pydantic.md) | `src/prismarine/prisma_client.py` | `model_library='pydantic'` | `tests/test_pydantic.py` | `pytest tests/test_pydantic.py` |
| Configure DynamoDB access | [Architecture: Dynamo Access](./architecture/dynamo-access.md) | `src/prismarine/runtime/dynamo_default.py`, `src/prismarine/prisma_client.py` | `get_dynamo_access()`, `--dynamo-access-module` | `tests/test_dynamo_access.py` | `pytest tests/test_dynamo_access.py` |
| Add triggers for EasySAM | [Integrations: EasySAM](./integrations/easysam.md) | `src/prismarine/runtime/cluster.py` | `TriggerConfig`, `trigger` parameter | `tests/test_triggers.py` | `pytest tests/test_triggers.py` |
| CLI command changes | [API: CLI Reference](./api/cli.md) | `src/prismarine/cli.py` | `prismarine generate-client`, `prismarine version` | `tests/test_cli.py` | `prismarine --help` |

## Core Concepts

### 1. Models
Models are defined using Python's `TypedDict` (default) or `pydantic.BaseModel` classes and decorated with the `Cluster.model()` decorator to specify primary and sort keys.

### 2. Clusters
The `Cluster` class groups related models together and sets a prefix for table names.

### 3. Auto-generated Client
The `prismarine_client.py` file is automatically generated and contains classes and methods for interacting with DynamoDB tables based on your defined models.

### 4. CRUD Operations
Generated models include static methods for all CRUD operations: `list()`, `get()`, `put()`, `update()`, `save()`, `delete()`, and `scan()`.

## Basic Usage

### Installation

```bash
pip install prismarine
```

### Directory Structure

```
<base-path>/
  <package-name>/
    - models.py
    - db.py
    - prismarine_client.py  # Auto-generated
```

### Define a Model

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

### Generate the Client

```bash
prismarine generate-client --base <base-path> <package-name>
```

### Use the Generated Client

```python
from <package-name>.prismarine_client import TeamModel

# Put an item
TeamModel.put({'Foo': 'team1', 'Bar': 'info', 'Baz': 'value'})

# Get an item
team = TeamModel.get(foo='team1', bar='info')

# List items
teams = TeamModel.list(foo='team1')
```

## Next Steps

- **[Architecture Overview](./architecture/overview.md)** - Learn about the system architecture
- **[Domain: Models](./domain/models.md)** - Detailed model definition guide
- **[Workflows: Client Generation](./workflows/client-generation.md)** - How client generation works
- **[API: CLI Reference](./api/cli.md)** - All CLI commands and options
- **[Integrations: EasySAM](./integrations/easysam.md)** - DynamoDB Stream Triggers
- **[Domain: Pydantic Support](./domain/pydantic.md)** - Using Pydantic models

## Change Navigation

- **When to consult this page**: When starting with Prismarine or planning a new feature
- **Runtime invariants**: Generated client must be importable and functional
- **Extension points**: Model decorators, CLI commands, DynamoDB access modules
- **Source files**: `src/prismarine/cluster.py`, `src/prismarine/cli.py`, `src/prismarine/prisma_client.py`
- **Focused tests**: `tests/test_cluster.py`, `tests/test_cli.py`, `tests/test_generate_client.py`
- **Validation**: Run `prismarine version` to verify installation