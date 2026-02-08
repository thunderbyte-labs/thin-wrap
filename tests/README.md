# Tests for Thin Wrap

This directory contains tests for the Thin Wrap LLM Terminal Chat application.

## Running Tests

Tests can be run using the virtual environment's Python:

```bash
cd /path/to/thin-wrap
./.venv/bin/python tests/test_draft_nav.py
```

Or from the tests directory:

```bash
cd tests
../.venv/bin/python test_draft_nav.py
```

## Test Files

- `test_draft_nav.py`: Tests for draft stack and message history navigation logic.

## Adding New Tests

When adding new test files:

1. Place them in this `tests/` directory
2. Use the following import pattern to access modules from the parent directory:

```python
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from module_name import ClassName
```

3. Name test files with `test_` prefix (e.g., `test_input_handler.py`, `test_command_handler.py`)

## Test Philosophy

Tests should:
- Be self-contained and not modify the actual application state
- Use simulation rather than requiring actual LLM API calls
- Focus on core logic and edge cases
- Be runnable without network connectivity