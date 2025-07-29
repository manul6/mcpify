import asyncio
import inspect
import json
from typing import Any, Dict, List

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolRequest, 
    ListToolsRequest, 
    TextContent, 
    Tool, 
    INVALID_PARAMS, 
    INTERNAL_ERROR
)

from function_schema import FunctionSchema
from callable_inspector import CallableInspector
from value_serializer import ValueSerializer
from mcp_types import TypeRegistry


class ToolError(Exception):
    pass


class FunctionTool:
    def __init__(self, func: Any, schema: FunctionSchema):
        self._func = func
        self._schema = schema
    
    async def __call__(self, **kwargs) -> Any:
        if self._schema.positional_parameters:
            positional_args = []
            remaining_kwargs = {}
            
            for param in self._schema.parameters:
                if param.is_positional and param.name in kwargs:
                    positional_args.append(kwargs[param.name])
                elif not param.is_positional and param.name in kwargs:
                    remaining_kwargs[param.name] = kwargs[param.name]
            
            if remaining_kwargs:
                return self._func(*positional_args, **remaining_kwargs)
            else:
                return self._func(*positional_args)
        else:
            return self._func(**kwargs)


class ToolHolder:
    def __init__(self, name: str = ""):
        self.name = name
        self.tools: Dict[str, FunctionTool] = {}
        self.schemas: Dict[str, FunctionSchema] = {}
    
    def add_tool(self, name: str, func: Any, schema: FunctionSchema):
        if not name:
            raise ToolError("tool name cannot be empty")
        if not callable(func):
            raise ToolError(f"tool '{name}' must be callable")
        if name in self.tools:
            raise ToolError(f"tool '{name}' already exists")
        
        if inspect.isclass(func):
            TypeRegistry.register(name, func)
        
        if schema.return_type and hasattr(schema.return_type, 'type_name') and schema.return_type.type_name:
            if inspect.isclass(func):
                TypeRegistry.register(schema.return_type.type_name, func)
        
        self.tools[name] = FunctionTool(func, schema)
        self.schemas[name] = schema
    
    def __iadd__(self, other: "FunctionTool | ToolHolder"):
        if isinstance(other, FunctionTool):
            if not other._schema or not hasattr(other._schema, 'name'):
                raise ToolError("functiontool must have a schema with name")
            tool_name = other._schema.name
            if not tool_name:
                raise ToolError("tool name is required")
            if tool_name in self.tools:
                raise ToolError(f"tool '{tool_name}' already exists")
            self.tools[tool_name] = other
            self.schemas[tool_name] = other._schema
        elif isinstance(other, ToolHolder):
            for name, tool in other.tools.items():
                if name in self.tools:
                    raise ToolError(f"tool '{name}' already exists")
                self.tools[name] = tool
                self.schemas[name] = other.schemas[name]
        else:
            raise ToolError("expected functiontool or toolholder")
        return self
    
    def __ior__(self, other: "ToolHolder"):
        if not isinstance(other, ToolHolder):
            raise ToolError("expected toolholder")
        if self.name and other.name and self.name != other.name:
            raise ToolError("holders must have same name")
        
        for name, tool in other.tools.items():
            if name in self.tools:
                raise ToolError(f"tool '{name}' already exists in target holder")
            self.tools[name] = tool
            self.schemas[name] = other.schemas[name]
        
        return self


class McpifiedServer:
    def __init__(self, name: str = "mcpify"):
        self.server = Server(name)
        self.tool_holder = ToolHolder(name)
        self.callable_inspector = CallableInspector()
        self.value_serializer = ValueSerializer()
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [schema.to_mcp_tool() for schema in self.tool_holder.schemas.values()]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
            try:
                if name not in self.tool_holder.tools:
                    raise ToolError(f"unknown tool: {name}")
                
                tool = self.tool_holder.tools[name]
                schema = self.tool_holder.schemas[name]
                
                raw_args = arguments or {}
                
                deserialized_args = {}
                for param in schema.parameters:
                    if param.name in raw_args:
                        raw_value = raw_args[param.name]
                        deserialized_args[param.name] = param.type.deserialize_value(raw_value)
                
                result = await tool(**deserialized_args)
                
                serialized_result = self.value_serializer.serialize(result)
                
                if isinstance(serialized_result, str):
                    result_text = serialized_result
                else:
                    result_text = json.dumps(serialized_result, default=str)
                
                return [TextContent(type="text", text=result_text)]
                    
            except Exception as e:
                return [TextContent(type="text", text=f"error: {e}")]
    
    def add_function(self, func: Any, name: str = None) -> 'McpifiedServer':
        function_name = name or getattr(func, '__name__', str(func))
        schema = self.callable_inspector.inspect_callable(func)
        self.tool_holder.add_tool(function_name, func, schema)
        return self
    
    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=self.server.name,
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


def mcpify(*callables, server_name: str = "mcpify") -> McpifiedServer:
    server = McpifiedServer(server_name)
    for callable_obj in callables:
        server.add_function(callable_obj)
    return server