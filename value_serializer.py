import inspect
import json
from typing import Any, Dict, List
from mcp_types import MCPType, MCP_INT, MCP_FLOAT, MCP_STRING, MCP_BOOL, MCPArray, MCPObject
from callable_inspector import TypeConverter
import pointer_registry


class ValueSerializer:
    def __init__(self, use_pointers: bool = True):
        self.type_converter = TypeConverter()
        self.use_pointers = use_pointers
    
    def serialize(self, value: Any) -> Any:
        # check if value is already a pointer envelope
        if isinstance(value, dict) and "__mcp_ptr__" in value:
            return json.dumps(value)
        
        # check if value is a primitive type
        if isinstance(value, (int, float, str, bool, type(None))):
            mcp_type = self.type_converter.convert_from_value(value)
            return mcp_type.serialize_value(value)
        
        # check if value is a simple list or dict without custom types
        if isinstance(value, (list, dict)) and not hasattr(value, '__class__') or value.__class__ in (list, dict):
            mcp_type = self.type_converter.convert_from_value(value)
            return mcp_type.serialize_value(value)
        
        # for complex objects, use pointer system if enabled
        if self.use_pointers and hasattr(value, '__dict__'):
            obj_id = pointer_registry.register(value)
            pointer_envelope = {
                "__mcp_ptr__": True,
                "type": value.__class__.__name__,
                "id": obj_id,
                "attrs": list(value.__dict__.keys()) if hasattr(value, '__dict__') else []
            }
            return json.dumps(pointer_envelope)
        
        # fallback to original serialization
        from mcp_types import MCP_STRING
        return MCP_STRING.serialize_value(value)


value_serializer = ValueSerializer() 