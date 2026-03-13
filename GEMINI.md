# Prismarine - DynamoDB ORM

Prismarine is a Pythonic ORM for DynamoDB that simplifies database interactions through code generation. Developers define models using standard Python types (`TypedDict` or `Pydantic`), and Prismarine generates a robust, type-safe client for performing CRUD operations.

## Project Overview

- **Core Technology**: Python (3.12+), Boto3, Mako (templating), Click (CLI).
- **Architecture**:
    - **Models**: Defined in `models.py` using decorators from a `Cluster` instance.
    - **CLI**: The `prismarine` command-line tool triggers the generation process.
    - **Generator**: Uses Mako templates (`src/prismarine/model.mako`) to produce `prismarine_client.py`.
    - **Runtime**: A set of lightweight utilities and base classes (`src/prismarine/runtime/`) that the generated client uses at execution time.
- **EasySAM Integration**: Supports metadata for DynamoDB Streams (triggers) and TTL, enabling automatic infrastructure configuration when used with EasySAM.

## Building and Running

### Environment Setup
The project uses `uv` for dependency management.
```powershell
# Install dependencies
uv sync

# Install optional Pydantic support
uv sync --extra pydantic
```

### Key Commands
- **Generate Client**:
  ```powershell
  prismarine generate-client --base <base-path> <package-name>
  ```
- **Run Tests**:
  ```powershell
  pytest
  ```
- **Linting**:
  ```powershell
  ruff check .
  ```
- **Formatting**:
  ```powershell
  ruff format .
  ```

## Development Conventions

### Model Definition
- Models should be defined in a `models.py` file within their respective package.
- **TypedDict (Default)**: Best for lightweight, dictionary-based models.
- **Pydantic**: Optional; provides runtime validation and better integration with modern Python web frameworks.
- Use `@cluster.model(PK='...', SK='...')` to define the primary key structure.
- Use `@cluster.index(index='...', PK='...', SK='...')` *above* the model decorator to define Global Secondary Indexes (GSIs).

### Code Style
- **Formatting**: The project adheres to `ruff` formatting standards with a preference for **single quotes**.
- **Type Safety**: Leverage Python type hints extensively. The generated client relies on these for static analysis and IDE support.
- **Explicit Arguments**: The generated client methods (e.g., `get`, `update`, `delete`) primarily use keyword-only arguments to prevent errors when field names change.

### Testing
- New features or changes to the generation logic should be verified in `tests/test_prisma_client_generation.py`.
- Tests typically involve mocking the file system or using temporary directories to verify the content of generated Python files.
