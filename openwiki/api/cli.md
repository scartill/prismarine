---
type: API Reference
title: CLI Reference
resource: https://github.com/scartill/prismarine
openwiki:
  roles: [api, workflow]
  change_kinds: [public-api, configuration]
  source_paths: [src/prismarine/cli.py]
  symbols: [prismarine, generate_client_cmd, version_cmd]
  test_paths: [tests/test_cli.py]
  invariants: [CLI commands must be functional and documented, Help text must be accurate]
  validation_commands: [prismarine --help, prismarine generate-client --help, prismarine version]
---

# CLI Reference

The Prismarine CLI provides commands for client generation and version information.

## Main Command

```bash
prismarine [OPTIONS] COMMAND [ARGS]...
```

**Global Options:**
- `--path`: Additional Python path to use (multiple allowed)
- `--verbose`: Enable verbose logging

**Commands:**
- `generate-client`: Generate a Prismarine client for a given cluster package
- `version`: Print the version of Prismarine

## generate-client Command

Generate a Prismarine client for DynamoDB operations based on model definitions.

```bash
prismarine generate-client [OPTIONS] CLUSTER_PACKAGE
```

### Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `--base` | PATH | Yes | Primary Python path to use while searching for 'models' package |
| `--runtime` | TEXT | No | Parent package for models to use in runtime. If not provided, assume top-level |
| `--dynamo-access-module` | TEXT | No | Dynamo access module to use in runtime. If not provided, DefaultDynamoAccess access class from prismarine.runtime.dynamo_default will be used |
| `--extra-imports` | TEXT | No | Extra imports to add to the client in format: path.to.module:ClassName. Can be specified multiple times |
| `--model-library` | Choice | No | Model definitions to expect inside clusters. Choose from: typed-dict, pydantic. Default: typed-dict |

### Examples

**Basic Usage:**
```bash
prismarine generate-client --base . mypackage
```

**With Custom Runtime:**
```bash
prismarine generate-client --base . mypackage --runtime services
```

**With Pydantic Models:**
```bash
prismarine generate-client --base . mypackage --model-library pydantic
```

**With Custom Dynamo Access:**
```bash
prismarine generate-client --base . mypackage --dynamo-access-module myapp.dynamo
```

**With Extra Imports:**
```bash
prismarine generate-client --base . mypackage \
    --extra-imports myapp.utils:CustomEncoder \
    --extra-imports myapp.auth:AuthMiddleware
```

**Verbose Output:**
```bash
prismarine --verbose generate-client --base . mypackage
```

### Usage Notes

1. **Base Path**: Must be a valid Python path containing your models package
2. **Cluster Package**: The Python package containing your model definitions
3. **Model Discovery**: Models are discovered via `@Cluster.model()` decorators
4. **Output**: Generates `prismarine_client.py` in the cluster package

### Common Issues

**Module Not Found:**
- Ensure `--base` path is correct
- Verify models package exists in the base path
- Check that models are importable

**Import Errors:**
- Verify all model dependencies are available
- Check extra imports are correctly formatted
- Ensure Dynamo access module is importable

## version Command

Print the version of Prismarine.

```bash
prismarine version
```

**Output:**
```
1.6.0
```

**Use Cases:**
- Check installed version
- CI/CD version verification
- Debugging version mismatches

## Path Configuration

### Using --path Option

Add additional Python paths for model discovery:

```bash
prismarine --path /path/to/shared --path /path/to/custom generate-client --base . mypackage
```

**Use Cases:**
- Shared model definitions across projects
- Custom module paths
- Development environment setup

### Path Resolution

1. Paths are resolved in order
2. Later paths can override earlier ones
3. All paths must exist
4. Paths are added to Python path for model discovery

## Verbose Mode

Enable detailed logging:

```bash
prismarine --verbose generate-client --base . mypackage
```

**Output Includes:**
- Discovery process details
- Model registration information
- Generation steps
- File operations
- Any warnings or errors

## Change Navigation

- **When to consult this page**: When using the CLI, troubleshooting command issues, or extending CLI functionality
- **Runtime invariants**:
  - CLI commands must be functional and documented
  - Help text must be accurate
  - Version command must return correct version
  - All options must work as documented
- **Extension points**:
  - New CLI commands
  - Additional options for existing commands
  - Custom path handling
  - Verbose logging improvements
- **Source files**:
  - `src/prismarine/cli.py` (CLI implementation)
  - `src/prismarine/prisma_client.py` (generation logic called by CLI)
- **Focused tests**:
  - `tests/test_cli.py` (CLI interface tests)
  - `tests/test_cli_options.py` (option parsing tests)
- **Validation**:
  - `prismarine --help` (main help)
  - `prismarine generate-client --help` (generate-client help)
  - `prismarine version` (version check)
  - `pytest tests/test_cli.py -v` (run CLI tests)

## Command Implementation Details

### Main CLI Structure

```python
@click.group()
@click.pass_context
@click.option('--path', multiple=True, type=click.Path(exists=True), help='Additional Python path to use')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def prismarine(ctx, path, verbose):
    ctx.ensure_object(dict)
    lg.basicConfig(level=lg.DEBUG if verbose else lg.INFO)
    paths = list(Path(p).resolve() for p in path) if path else []
    set_path(paths)
```

**Key Features:**
- Click-based command group
- Multiple path support
- Verbose logging configuration
- Context object for state management

### generate-client Command Implementation

```python
@prismarine.command(name='generate-client', help='Generate a Prismarine client for a given cluster package')
@click.option('--base', required=True, type=click.Path(exists=True), help="Primary Python path to use while searching for 'models' package")
@click.option('--runtime', required=False, help='Parent package for models to use in runtime. If not provided, assume top-level')
@click.option('--dynamo-access-module', required=False, help='Dynamo access module to use in runtime...')
@click.option('--extra-imports', required=False, multiple=True, help='Extra imports to add to the client in format: path.to.module:ClassName')
@click.option('--model-library', type=click.Choice(['typed-dict', 'pydantic'], case_sensitive=False), default='typed-dict', show_default=True, help='Model definitions to expect inside clusters...')
@click.argument('cluster_package')
def generate_client_cmd(base, runtime, dynamo_access_module, cluster_package, extra_imports, model_library):
    base_dir = Path(base)
    if extra_imports:
        extra_imports = [i.split(':') for i in extra_imports]
    generate_client(
        base_dir,
        cluster_package,
        runtime=runtime,
        access_module=dynamo_access_module,
        extra_imports=extra_imports,
        model_library=model_library.replace('-', '_'),
    )
```

**Key Features:**
- Required base path argument
- Multiple option types (required, optional, choice)
- Extra imports parsing
- Model library selection
- Calls `generate_client()` function

### version Command Implementation

```python
@prismarine.command(name='version', help='Print the version of Prismarine')
def version_cmd():
    click.echo(version('prismarine'))
```

**Key Features:**
- Simple version retrieval
- Uses importlib.metadata.version()
- Clean output formatting

## Common Patterns

### Development Script

```bash
#!/bin/bash
# regenerate.sh

set -e

echo "Regenerating Prismarine client..."
prismarine generate-client --base . mypackage

echo "Running tests..."
pytest tests/

echo "Client generation complete!"
```

### CI/CD Integration

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e .[pydantic]
      - name: Generate client
        run: prismarine generate-client --base . mypackage
      - name: Run tests
        run: pytest tests/
```

### Local Development with Custom Paths

```bash
# Add shared models directory to path
prismarine --path ../shared-models generate-client --base . mypackage
```

### Debugging Generation Issues

```bash
# Enable verbose logging
prismarine --verbose generate-client --base . mypackage

# Check what's being generated
prismarine generate-client --base . mypackage > output.py
cat output.py
```

## Troubleshooting

### Command Not Found

**Problem**: `prismarine: command not found`

**Solution**:
1. Verify Prismarine is installed: `pip show prismarine`
2. Check installation: `pip install prismarine`
3. Verify Python environment: `which python`
4. Check PATH includes Python scripts directory

### Invalid Base Path

**Problem**: `Error: Invalid value for '--base': Path '/wrong/path' does not exist`

**Solution**:
1. Verify path exists: `ls /wrong/path`
2. Use absolute path if needed
3. Check current directory: `pwd`
4. Verify path contains models package

### Model Discovery Failure

**Problem**: No models found in generated client

**Solution**:
1. Verify models use `@Cluster.model()` decorator
2. Check models are in a Python package
3. Ensure package has `__init__.py`
4. Use `--verbose` to see discovery process

### Import Errors in Generated Client

**Problem**: Generated client has import errors

**Solution**:
1. Verify all model dependencies are available
2. Check extra imports are correctly formatted
3. Ensure Dynamo access module is importable
4. Check Python path includes all required modules

### Version Mismatch

**Problem**: Wrong version displayed

**Solution**:
1. Reinstall Prismarine: `pip install --force-reinstall prismarine`
2. Check installed version: `pip show prismarine`
3. Verify package metadata
4. Check for multiple installations

### Permission Issues

**Problem**: Permission denied when generating client

**Solution**:
1. Check write permissions: `ls -la mypackage/`
2. Use sudo if necessary (not recommended)
3. Change ownership: `chown -R $USER mypackage/`
4. Check directory permissions: `chmod -R u+w mypackage/`

## Extending the CLI

### Adding New Commands

1. Add new function with `@prismarine.command()` decorator
2. Define options with `@click.option()` decorators
3. Implement command logic
4. Add tests
5. Update documentation

**Example:**
```python
@prismarine.command(name='validate')
def validate_cmd():
    """Validate model definitions"""
    click.echo("Validating models...")
    # Validation logic here
    click.echo("Models are valid!")
```

### Adding Options to Existing Commands

1. Add new `@click.option()` to existing command
2. Pass option to underlying function
3. Update help text
4. Add tests
5. Document the new option

**Example:**
```python
@prismarine.command(name='generate-client')
@click.option('--check', is_flag=True, help='Check if client needs regeneration')
def generate_client_cmd(..., check):
    if check:
        # Check logic here
        pass
```

### Custom Path Handling

The `set_path()` function in `prisma_common.py` manages Python path configuration:

```python
from pathlib import Path
import sys

def set_path(paths):
    """Add paths to Python path"""
    for path in paths:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
```

**Customization Points:**
- Modify path insertion order
- Add validation for paths
- Support environment variables
- Add path caching