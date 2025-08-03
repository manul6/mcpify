import asyncio
import inspect
import json
import types
import pkgutil
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
        self._has_self = any(param.name == 'self' for param in self._schema.parameters)
    
    async def __call__(self, *args, **kwargs) -> Any:
        if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            function_args = args[0]
        elif len(args) == 0 and kwargs:
            if self._has_self:
                raise TypeError("function has 'self' parameter - must pass arguments as dict to avoid naming conflicts")
            function_args = kwargs
        elif len(args) == 0 and not kwargs:
            function_args = {}
        else:
            raise TypeError("pass either a single dict argument or keyword arguments, not both")
        
        if self._schema.positional_parameters:
            positional_args = []
            remaining_kwargs = {}
            for param in self._schema.parameters:
                if param.is_positional and param.name in function_args:
                    positional_args.append(function_args[param.name])
                elif not param.is_positional and param.name in function_args:
                    remaining_kwargs[param.name] = function_args[param.name]
            return self._func(*positional_args, **remaining_kwargs) if remaining_kwargs else self._func(*positional_args)
        return self._func(**function_args)


class ToolHolder:
    def __init__(self, name: str = ""):
        self.name = name
        self.tools: Dict[str, FunctionTool] = {}
        self.schemas: Dict[str, FunctionSchema] = {}
        self.callable_inspector = CallableInspector()
    
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
    
    def __ior__(self, other: "ToolHolder"):
        if not isinstance(other, ToolHolder):
            raise ToolError("expected ToolHolder")
        
        for name, tool in other.tools.items():
            if name in self.tools:
                raise ToolError(f"tool '{name}' already exists")
            self.tools[name] = tool
            self.schemas[name] = other.schemas[name]
        
        return self
    
    def __iadd__(self, other: "FunctionTool"):
        if not isinstance(other, FunctionTool):
            raise ToolError("expected FunctionTool")
        if not other._schema or not hasattr(other._schema, 'name'):
            raise ToolError("FunctionTool must have a schema with name")
        
        tool_name = other._schema.name
        if not tool_name:
            raise ToolError("tool name is required")
        if tool_name in self.tools:
            raise ToolError(f"tool '{tool_name}' already exists")
        
        self.tools[tool_name] = other
        self.schemas[tool_name] = other._schema
        return self


class McpifiedServer:
    def __init__(self, name: str = "mcpify"):
        self.server = Server(name)
        self.tool_holder = ToolHolder(name)
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
                
                result = await tool(deserialized_args)
                
                serialized_result = self.value_serializer.serialize(result)
                
                if isinstance(serialized_result, str):
                    result_text = serialized_result
                else:
                    result_text = json.dumps(serialized_result, default=str)
                
                return [TextContent(type="text", text=result_text)]
                    
            except Exception as e:
                return [TextContent(type="text", text=f"error: {e}")]
    
    def __iadd__(self, other: "FunctionTool | ToolHolder"):
        if isinstance(other, FunctionTool):
            if not other._schema or not hasattr(other._schema, 'name'):
                raise ToolError("functiontool must have a schema with name")
            tool_name = other._schema.name
            if not tool_name:
                raise ToolError("tool name is required")
            if tool_name in self.tool_holder.tools:
                raise ToolError(f"tool '{tool_name}' already exists")
            self.tool_holder.tools[tool_name] = other
            self.tool_holder.schemas[tool_name] = other._schema
        elif isinstance(other, ToolHolder):
            for name, tool in other.tools.items():
                if name in self.tool_holder.tools:
                    raise ToolError(f"tool '{name}' already exists")
                self.tool_holder.tools[name] = tool
                self.tool_holder.schemas[name] = other.schemas[name]
        else:
            raise ToolError("expected functiontool or toolholder")
        return self
    
    def __ior__(self, other: "ToolHolder"):
        if not isinstance(other, ToolHolder):
            raise ToolError("expected toolholder")
        
        for name, tool in other.tools.items():
            if name in self.tool_holder.tools:
                raise ToolError(f"tool '{name}' already exists in target holder")
            self.tool_holder.tools[name] = tool
            self.tool_holder.schemas[name] = other.schemas[name]
        
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


def mcpify(*objects, server_name: str = "mcpify", max_depth: int = 10, _current_depth: int = 0, _name_prefix: str = "") -> McpifiedServer:
    if _current_depth >= max_depth:
        return McpifiedServer(server_name)
    
    def _should_include_attribute(name: str, obj: Any) -> bool:
        if name.startswith('_'):
            return False
        
        if isinstance(obj, types.ModuleType):
            skip_attrs = {'__builtins__', '__cached__', '__file__', '__loader__', 
                         '__name__', '__package__', '__spec__', '__path__', '__doc__'}
            if name in skip_attrs:
                return False
        
        return callable(obj) or inspect.isclass(obj) or inspect.ismodule(obj)
    
    def _get_tool_name(base_name: str, prefix: str = "") -> str:
        return f"{prefix}-{base_name}" if prefix else base_name
    
    def _add_module(module: types.ModuleType, name_prefix: str = "") -> ToolHolder:
        module_name = getattr(module, '__name__', 'module').split('.')[-1]
        current_prefix = _get_tool_name(module_name, name_prefix) if name_prefix else module_name
        
        tool_holder = ToolHolder(module_name)
        
        for attr_name in dir(module):
            try:
                attr_obj = getattr(module, attr_name)
                if not _should_include_attribute(attr_name, attr_obj):
                    continue
                
                if (hasattr(attr_obj, '__module__') and 
                    attr_obj.__module__ and 
                    attr_obj.__module__ != module.__name__):
                    continue
                
                sub_server = mcpify(
                    attr_obj, 
                    server_name="", 
                    max_depth=max_depth,
                    _current_depth=_current_depth + 1,
                    _name_prefix=current_prefix
                )
                tool_holder |= sub_server.tool_holder
                
            except (AttributeError, ImportError):
                continue
        
        if hasattr(module, '__path__'):
            try:
                for importer, modname, ispkg in pkgutil.iter_modules(module.__path__, module.__name__ + "."):
                    try:
                        submodule = __import__(modname, fromlist=[''])
                        sub_holder = _add_module(submodule, current_prefix)
                        tool_holder |= sub_holder
                    except (ImportError, AttributeError):
                        continue
            except (AttributeError, TypeError):
                pass
        
        return tool_holder
    
    def _add_class(cls: type, name_prefix: str = "") -> ToolHolder:
        class_name = cls.__name__
        current_prefix = _get_tool_name(class_name, name_prefix) if name_prefix else class_name
        
        tool_holder = ToolHolder(class_name)
        
        
        try:
            constructor_name = _get_tool_name('new', current_prefix)
            schema = tool_holder.callable_inspector.inspect_callable(cls)
            schema = FunctionSchema(
                name=constructor_name,
                description=f"Create new instance of {class_name}",
                parameters=schema.parameters,
                return_type=schema.return_type
            )
            tool_holder.add_tool(constructor_name, cls, schema)
        except Exception:
            pass
        
        for attr_name in dir(cls):
            if not _should_include_attribute(attr_name, cls):
                continue
            
            try:
                attr_obj = getattr(cls, attr_name)
                
                if callable(attr_obj) and attr_name != '__init__':
                    method_name = _get_tool_name(attr_name, current_prefix)
                    try:
                        schema = tool_holder.callable_inspector.inspect_callable(attr_obj)
                        schema = FunctionSchema(
                            name=method_name,
                            description=schema.description or f"{attr_name} method of {class_name}",
                            parameters=schema.parameters,
                            return_type=schema.return_type
                        )
                        tool_holder.add_tool(method_name, attr_obj, schema)
                    except Exception:
                        continue
                elif inspect.isclass(attr_obj):
                    sub_holder = _add_class(
                        attr_obj, 
                        current_prefix
                    )
                    tool_holder |= sub_holder
                    
            except (AttributeError, TypeError):
                continue
        
        return tool_holder
    
    def _add_callable(callable_obj: Any, name_prefix: str = "") -> ToolHolder:
        obj_name = getattr(callable_obj, '__name__', str(callable_obj))
        tool_name = _get_tool_name(obj_name, name_prefix) if name_prefix else obj_name
        
        try:
            tool_holder = ToolHolder(obj_name)
            schema = tool_holder.callable_inspector.inspect_callable(callable_obj)
            # Update schema name to include full path
            schema = FunctionSchema(
                name=tool_name,
                description=schema.description,
                parameters=schema.parameters,
                return_type=schema.return_type
            )
            tool_holder.add_tool(tool_name, callable_obj, schema)
            return tool_holder
        except Exception:
            return ToolHolder(obj_name)
    
    # Main processing logic
    server = McpifiedServer(server_name)
    
    for obj in objects:
        try:
            if inspect.ismodule(obj):
                server |= _add_module(obj, _name_prefix)
            elif inspect.isclass(obj):
                server |= _add_class(obj, _name_prefix)
            elif callable(obj):
                server |= _add_callable(obj, _name_prefix)
        except Exception:
            continue
    
    return server