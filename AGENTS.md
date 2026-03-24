# AGENTS.md

## Build/Test/Lint Commands

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run the web server
uv run planmode serve
# or
python planmode.py serve

# Run all tests
uv run pytest

# Run a single test file
uv run pytest test_file.py

# Run a specific test
uv run pytest test_file.py::test_function_name

# Run with verbose output
uv run pytest -v

# Run with coverage (if pytest-cov is installed)
uv run pytest --cov=planmode
```

## Code Style Guidelines

### General
- **Python version**: 3.11+ (use modern features like `list[T]`, `|` unions)
- **Line length**: 88-100 characters preferred
- **Trailing commas**: Use in multi-line structures
- **Quotes**: Double quotes for strings in code, single for docstrings

### Imports
Order: `__future__` → stdlib → third-party → local, with blank lines between groups:

```python
from __future__ import annotations
from pathlib import Path
import os

from pydantic import BaseModel, Field
import fasthtml.common as fh
import typer
```

### Formatting
- **Indentation**: 4 spaces
- **Blank lines**: 2 between top-level definitions, 1 between methods
- **Type hints**: Required on function signatures, use `list[T]` not `List[T]`
- **Trailing whitespace**: Remove

### Naming Conventions
- **Classes**: PascalCase (`Plan`, `Item`)
- **Functions/variables**: snake_case (`from_path`, `render_items`)
- **Constants**: UPPER_SNAKE_CASE (`REPO`)
- **Private**: Leading underscore for internal use

### Type Hints
- Use `from __future__ import annotations` for forward references
- Prefer built-in generics: `list[T]`, `dict[K, V]` over `typing.List`, `typing.Dict`
- Use `|` for unions: `str | None` instead of `Optional[str]`
- Annotate all function parameters and return types

### Error Handling
- Use assertions for programmer errors (invalid input structure)
- Use exceptions for runtime errors
- Provide descriptive error messages with context

```python
# Good
assert md.startswith("- "), f"Text is not a nested list!\n{md}"
assert index_md.is_file(), f"Index file is missing! {index_md}"

# Avoid bare except clauses
except Exception as error:  # OK with explicit binding
```

### Classes (Pydantic)
- Use `BaseModel` for data classes
- Use `Field(default_factory=list)` for mutable defaults
- Define recursive types with forward references

```python
class Item(BaseModel):
    name: str
    items: list[Item] = []  # Self-referential with forward annotations
```

### FastHTML Patterns
- Import as `fh` namespace
- Use `rt` decorator from `fast_app()` for routes
- Define reusable components as functions returning FH elements

### Architecture
- Single-file application (planmode.py)
- Keep models (Item, Plan) separate from web handlers
- Use classmethods for factory methods (`from_md`, `from_path`)
- Recursive data structures for tree-like content

### Documentation
- Add docstrings only when logic is non-obvious
- Prefer self-documenting code with clear names
- Comments should explain "why", not "what"

## Project Structure

```
planmode/
├── planmode.py          # Main application (single file)
├── pyproject.toml       # Dependencies and metadata
├── uv.lock             # Locked dependencies
└── tests/              # Tests (to be added)
```

## Testing Strategy

- Use pytest for all tests
- Test data models (Item, Plan) thoroughly
- Test markdown parsing roundtrips (to_md ↔ from_md)
- Use temporary directories for file-based tests
- No existing tests yet - create tests/ directory as needed
