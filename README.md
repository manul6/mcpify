# mcpify

a minimal library for converting python functions into mcp (model context protocol) tools.

## core functionality

mcpify provides a simple way to expose python functions as mcp tools with automatic schema generation and type conversion.

## usage

```python
from mcpify import mcpify

def add(a: int, b: int) -> int:
    """add two numbers"""
    return a + b

def greet(name: str) -> str:
    """greet someone"""
    return f"hello {name}!"

# create mcp server with functions
server = mcpify([add, greet])
```

## core components

- **mcpify.py**: main library with `mcpify()` function and server classes
- **callable_inspector.py**: function introspection and parameter extraction
- **mcp_types.py**: type system for mcp schema generation
- **function_schema.py**: schema representation for functions
- **schema_builders.py**: json schema generation
- **value_serializer.py**: value serialization for mcp responses

## example server

see `minimal_server.py` for a complete working example.

run with:
```bash
python minimal_server.py
```

## requirements

see `requirements.txt` for dependencies. 