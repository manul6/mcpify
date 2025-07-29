from abc import ABC, abstractmethod
from typing import Any, Dict

from mcp_types import (
    MCPType, MCPInt, MCPFloat, MCPString, MCPBool, MCPAny,
    MCPArray, MCPObject, MCPUnion, MCPOptional
)


class SchemaBuilder(ABC):
    @abstractmethod
    def build(self, mcp_type: MCPType) -> Dict[str, Any]:
        pass


class JSONSchemaBuilder(SchemaBuilder):
    def build(self, mcp_type: MCPType) -> Dict[str, Any]:
        return self._dispatch(mcp_type)
    
    def _dispatch(self, mcp_type: MCPType) -> Dict[str, Any]:
        type_name = type(mcp_type).__name__.lower()
        method_name = f"_build_{type_name}"
        
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            return method(mcp_type)
        else:
            raise ValueError(f"unsupported mcp type: {type(mcp_type)}")
    
    def _build_mcpany(self, mcp_type: MCPAny) -> Dict[str, Any]:
        return {
            "type": "string",
            "description": "json-serialized value of any type"
        }
    
    def _build_mcpint(self, mcp_type: MCPInt) -> Dict[str, Any]:
        return {"type": "integer"}
    
    def _build_mcpfloat(self, mcp_type: MCPFloat) -> Dict[str, Any]:
        return {"type": "number"}
    
    def _build_mcpstring(self, mcp_type: MCPString) -> Dict[str, Any]:
        return {"type": "string"}
    
    def _build_mcpbool(self, mcp_type: MCPBool) -> Dict[str, Any]:
        return {"type": "boolean"}
    
    def _build_mcparray(self, mcp_type: MCPArray) -> Dict[str, Any]:
        return {
            "type": "string",
            "description": f"json-serialized array with items of type: {type(mcp_type.items).__name__}"
        }
    
    def _build_mcpobject(self, mcp_type: MCPObject) -> Dict[str, Any]:
        schema = {
            "type": "string",
            "description": f"json-serialized object"
        }
        
        if mcp_type.type_name:
            schema["description"] += f" of type {mcp_type.type_name}"
        
        if mcp_type.properties:
            prop_desc = ", ".join(f"{name}: {type(prop_type).__name__}" for name, prop_type in mcp_type.properties.items())
            schema["description"] += f" with properties: {prop_desc}"
        
        if mcp_type.description:
            schema["description"] += f" - {mcp_type.description}"
            
        return schema
    
    def _build_mcpunion(self, mcp_type: MCPUnion) -> Dict[str, Any]:
        variant_types = [type(variant).__name__ for variant in mcp_type.variants]
        return {
            "type": "string",
            "description": f"json-serialized value that can be one of: {', '.join(variant_types)}"
        }
    
    def _build_mcpoptional(self, mcp_type: MCPOptional) -> Dict[str, Any]:
        inner_schema = self.build(mcp_type.inner_type)
        if "description" in inner_schema:
            inner_schema["description"] += " (optional, can be null)"
        return {
            "anyOf": [
                inner_schema,
                {"type": "null"}
            ]
        }


json_schema_builder = JSONSchemaBuilder() 