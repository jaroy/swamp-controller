# SWAMP Controller Tests

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_integration.py

# Run with coverage
pytest --cov=swamp
```

## Writing Tests

### Important: Never Use the Default Port

Integration tests should **never** use the default port (41794) to avoid conflicts with running instances.

**Good:**
```python
from tests.test_helpers import get_free_port

async def test_something():
    test_port = get_free_port()  # Get a free port dynamically
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)
```

**Bad:**
```python
async def test_something():
    tcp_server = SwampTcpServer(41794, protocol, state_manager)  # DON'T DO THIS
```

### Test Helpers

- `get_free_port()` - Returns an available port number for testing
- `TEST_PORT` - A fixed test port (41795) if you need consistency

### Async Tests

Tests use `pytest-asyncio` for async support:

```python
import pytest

@pytest.mark.asyncio
async def test_my_async_function():
    result = await some_async_function()
    assert result == expected
```

With `asyncio_mode = "auto"` in `pyproject.toml`, you can also just use:

```python
async def test_my_async_function():  # No decorator needed
    result = await some_async_function()
    assert result == expected
```

## Test Structure

```
tests/
├── README.md              # This file
├── __init__.py           # Package marker
├── test_helpers.py       # Test utilities
└── test_integration.py   # Integration tests
```

## CI/CD Considerations

Tests are designed to:
- Run in parallel without port conflicts (dynamic port allocation)
- Not require a real SWAMP device
- Clean up resources properly (cancel tasks, close connections)
- Complete quickly (< 1 second per test)
