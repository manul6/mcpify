import inspect
import json
from typing import Callable, Any, get_origin, get_args, Union
from mcp.types import Tool, CallToolResult, TextContent, CallToolRequest, CallToolRequestParams
from mcp.server import Server

def mcpify_type(annotation: Any) -> dict:
    """convert python type annotations to json schema"""
    if annotation is int:
        return {"type": "integer"}
    elif annotation is float:
        return {"type": "number"}
    elif annotation is str:
        return {"type": "string"}
    elif annotation is bool:
        return {"type": "boolean"}
    
    origin = get_origin(annotation)
    args = get_args(annotation)
    
    if origin is list:
        return {"type": "array", "items": mcpify_type(args[0]) if args else {}}
    elif origin is dict:
        return {"type": "object"}
    
    return {"type": "string"}

def mcpify_function(func: Callable) -> Tool:
    """convert function to mcp tool
    
    >>> def multiply(x: int, y: int) -> int:
    ...     return x * y
    >>> tool = mcpify_function(multiply)
    >>> tool # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    Tool(name='multiply', ..., inputSchema={'type': 'object', 'properties': {'x': {'type': 'integer'}, 'y': {'type': 'integer'}}, 'required': ['x', 'y']}...)
    """
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        if param.annotation != inspect.Parameter.empty:
            properties[param_name] = mcpify_type(param.annotation)
        else:
            properties[param_name] = {"type": "string"}
            
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    return Tool(
        name=func.__name__,
        description=func.__doc__,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required
        }
    )

class McpifiedServer(Server):
    def __init__(self, name: str = ""):
        """
        >>> server = McpifiedServer()
        >>> def add(x: int, y: int) -> int:
        ...     return x + y
        >>> server.add_function(add) # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
        Tool(name='add', ..., inputSchema={'type': 'object', 'properties': {'x': {'type': 'integer'}, 'y': {'type': 'integer'}}, 'required': ['x', 'y']}...)
        >>> server.functions # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
        {'add': <function add at ...>}
        >>> request = CallToolRequest(method="tools/call", params=CallToolRequestParams(
        ...     name="add",
        ...     arguments={"x": 1, "y": 2}
        ... ))
        >>> import asyncio
        >>> asyncio.run(server._handle_call_tool(request)) # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
        CallToolResult(..., content=[TextContent(type='text', text='3', ...)], ..., isError=False)
        """
        super().__init__(name)
        self.functions = {}
    
    def add_function(self, func: Callable):
        tool = mcpify_function(func)
        self.functions[func.__name__] = func
        return tool
    
    async def _handle_call_tool(self, request):
        tool_name = request.params.name
        arguments = request.params.arguments
        
        if tool_name not in self.functions:
            return CallToolResult(
                content=[TextContent(type="text", text=f"tool '{tool_name}' not found")]
            )
        
        try:
            func = self.functions[tool_name]
            result = await func(**arguments) if inspect.iscoroutinefunction(func) else func(**arguments)
            result_text = json.dumps(result) if not isinstance(result, str) else result
            
            return CallToolResult(
                content=[TextContent(type="text", text=result_text)]
            )
        except Exception as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"error: {str(e)}")]
            )

def mcpify(func_or_list: Callable | list[Callable]) -> McpifiedServer:
    server = McpifiedServer()
    
    if callable(func_or_list):
        server.add_function(func_or_list)
    elif isinstance(func_or_list, list):
        for func in func_or_list:
            server.add_function(func)
    
    return server