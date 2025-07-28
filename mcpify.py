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

def mcpify_function(func: Callable) -> "FunctionTool":
    """convert function to mcp tool
    
    >>> def multiply(x: int, y: int) -> int:
    ...     return x * y
    >>> tool = mcpify_function(multiply)
    >>> tool # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    Tool(name='multiply', ..., inputSchema={'type': 'object', 'properties': {'x': {'type': 'integer'}, 'y': {'type': 'integer'}}, 'required': ['x', 'y']}...)
    """
    return FunctionTool(func)

class FunctionTool(Tool):
    def __init__(self, func: Callable):
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
                
        super().__init__(
            name=func.__name__,
            description=func.__doc__,
            inputSchema={
                "type": "object",
                "properties": properties,
                "required": required
            }
        )
        self._func = func
    
    def __call__(self, **kwargs):
        return self._func(**kwargs)
    
class ToolHolder:
    def __init__(self, name: str = "", tools: dict[str, "ToolHolder | FunctionTool"] | None = None):
        self.name = name
        self.tools : dict[str, "ToolHolder | FunctionTool"] = tools or {}
    
    def __iadd__(self, other: "FunctionTool | ToolHolder"):
        assert other.name, "tool name is required"
        self.tools[other.name] = other
        return self
    
    def __ior__(self, other: "ToolHolder"):
        assert isinstance(other, ToolHolder), "a tool"
        assert self.name == other.name, "should be the same name"
        assert not set(self.tools.keys()) & set(other.tools.keys()), "overlapping tool names found"
        
        self.tools.update(other.tools)
        return self
    
    def __getitem__(self, name: str) -> "ToolHolder | FunctionTool":
        next, path = name.split(".", 1) if "." in name else (name, "")
        tool = self.tools[next]
        if isinstance(tool, ToolHolder):
            return tool[path]
        else:
            assert not path, "no such path"
            return tool
    
    def __call__(self, tool_name: str, **kwargs) -> Any:
        return self[tool_name](**kwargs)
        

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
        self.tools = ToolHolder()
        
        @self.list_tools()
        async def handle_list_tools():
            return [tool for tool in self.tools.tools.values() if isinstance(tool, FunctionTool)]
        
        @self.call_tool()
        async def handle_call_tool(name: str, arguments: dict):
            try:
                tool = self.tools[name]
                result = await tool(**arguments) if inspect.iscoroutinefunction(tool._func) else tool(**arguments)
                result_text = json.dumps(result) if not isinstance(result, str) else result
            except Exception as e:
                result_text = f"error: {str(e)}"
            
            return [TextContent(type="text", text=result_text)]
    
    def add_function(self, func: Callable):
        tool = mcpify_function(func)
        self.tools += tool
        return tool

def mcpify(func_or_list: Callable | list[Callable]) -> McpifiedServer:
    server = McpifiedServer()
    
    if callable(func_or_list):
        server.add_function(func_or_list)
    elif isinstance(func_or_list, list):
        for func in func_or_list:
            server.add_function(func)
    
    return server