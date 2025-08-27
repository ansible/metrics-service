# UV Dependency Management Setup

This project has been configured to use `uv` for modern Python dependency management.

## Quick Start

```bash
# Install all dependencies
uv sync

# Install with development dependencies
uv sync --extra dev

# Install with test dependencies
uv sync --extra test

# Install with LDAP support
uv sync --extra ldap

# Install with all extras
uv sync --all-extras
```

## Project Structure

- **`pyproject.toml`** - Main project configuration with all dependencies
- **`uv.lock`** - Locked dependency versions (auto-generated)
- **`requirements.txt`** - Legacy compatibility (points to pyproject.toml)

## Available Dependency Groups

### Core Dependencies

Automatically installed with `uv sync`:

- Django & DRF
- Database drivers (PostgreSQL)
- Redis
- Authentication packages
- Core Django extensions

### Optional Dependencies

Install with `--extra <group>`:

- **`dev`** - Development tools (black, ruff, mypy, pre-commit)
- **`test`** - Testing tools (pytest, coverage, factory-boy)
- **`ldap`** - LDAP authentication support
- **`docs`** - Documentation tools (sphinx)

## Common Commands

```bash
# Update dependencies
uv lock

# Add a new dependency
uv add <package>

# Add a development dependency
uv add --dev <package>

# Remove a dependency
uv remove <package>

# Run tests
uv run pytest

# Run Django management commands
uv run python manage.py <command>
```

## Migration from pip/requirements.txt

The project dependencies are now fully managed through `pyproject.toml`. The `requirements.txt` file is kept for legacy compatibility but simply installs the project in editable mode.

For the best experience, use `uv` commands instead of `pip` for all dependency management.
