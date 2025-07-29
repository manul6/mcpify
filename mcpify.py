import inspect
import json
from typing import Callable, Any, List
from mcp.types import Tool, CallToolResult, TextContent
from mcp.server import Server

from callable_inspector import callable_inspector
from function_schema import FunctionSchema
from value_serializer import value_serializer


class ToolError(Exception):
    """custom exception for tool-related errors"""
    pass


class FunctionTool(Tool):
    def __init__(self, func: Callable, schema: FunctionSchema):
        super().__init__(
            name=schema.name,
            description=schema.description,
            inputSchema=schema.to_mcp_tool().inputSchema
        )
        self._func = func
        self._schema = schema
    
    def __call__(self, **kwargs):
        return self._func(**kwargs)


class ToolHolder:
    def __init__(self, name: str = "", tools: dict[str, "ToolHolder | FunctionTool"] | None = None):
        self.name = name
        self.tools: dict[str, "ToolHolder | FunctionTool"] = tools or {}
    
    def __iadd__(self, other: "FunctionTool | ToolHolder"):
        if not other.name:
            raise ToolError("tool name is required")
        self.tools[other.name] = other
        return self
    
    def __ior__(self, other: "ToolHolder"):
        if not isinstance(other, ToolHolder):
            raise ToolError("expected ToolHolder")
        if self.name != other.name:
            raise ToolError("holders must have same name")
        
        overlapping_keys = set(self.tools.keys()) & set(other.tools.keys())
        if overlapping_keys:
            raise ToolError(f"overlapping tool names: {overlapping_keys}")
        
        self.tools.update(other.tools)
        return self
    
    def __getitem__(self, name: str) -> "ToolHolder | FunctionTool":
        next_part, path = name.split(".", 1) if "." in name else (name, "")
        
        if next_part not in self.tools:
            raise ToolError(f"tool not found: {next_part}")
        
        tool = self.tools[next_part]
        
        if isinstance(tool, ToolHolder):
            return tool[path] if path else tool
        else:
            if path:
                raise ToolError(f"no such path: {path}")
            return tool
    
    def __call__(self, tool_name: str, **kwargs) -> Any:
        return self[tool_name](**kwargs)


class McpifiedServer(Server):
    def __init__(self, name: str = ""):
        super().__init__(name)
        self.tools = ToolHolder()
        
        @self.list_tools()
        async def handle_list_tools():
            return [tool for tool in self.tools.tools.values() if isinstance(tool, FunctionTool)]
        
        @self.call_tool()
        async def handle_call_tool(name: str, arguments: dict):
            try:
                tool = self.tools[name]
                
                if inspect.iscoroutinefunction(tool._func):
                    result = await tool(**arguments)
                else:
                    result = tool(**arguments)
                
                serialized_result = value_serializer.serialize(result)
                result_text = json.dumps(serialized_result, default=str)
                
                return [TextContent(type="text", text=result_text)]
                    
            except Exception as e:
                error_text = f"error: {str(e)}"
                return [TextContent(type="text", text=error_text)]
    
    def add_function(self, func: Callable) -> FunctionTool:
        schema = callable_inspector.inspect_callable(func)
        tool = FunctionTool(func, schema)
        self.tools += tool
        return tool


def mcpify(func_or_list: Callable | List[Callable]) -> McpifiedServer:
    server = McpifiedServer()
    
    if callable(func_or_list):
        server.add_function(func_or_list)
    elif isinstance(func_or_list, list):
        for func in func_or_list:
            if callable(func):
                server.add_function(func)
    
    return server