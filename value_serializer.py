import inspect
from typing import Any, Dict, List
from mcp_types import MCPType, MCP_INT, MCP_FLOAT, MCP_STRING, MCP_BOOL, MCPArray, MCPObject
from callable_inspector import TypeConverter


class ValueSerializer:
    def __init__(self):
        self.type_converter = TypeConverter()
    
    def serialize(self, value: Any) -> Any:
        mcp_type = self.type_converter.convert_from_value(value)
        return mcp_type.serialize_value(value)


value_serializer = ValueSerializer() 