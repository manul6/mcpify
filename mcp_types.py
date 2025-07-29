from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Union


@dataclass(frozen=True)
class MCPType(ABC):
    @abstractmethod
    def serialize_value(self, value: Any) -> Any:
        pass
    
    @abstractmethod
    def deserialize_value(self, data: Any) -> Any:
        pass


@dataclass(frozen=True)
class MCPPrimitive(MCPType):
    pass


@dataclass(frozen=True)
class MCPInt(MCPPrimitive):
    def serialize_value(self, value: Any) -> int:
        return int(value)
    
    def deserialize_value(self, data: Any) -> int:
        return int(data)


@dataclass(frozen=True)
class MCPFloat(MCPPrimitive):
    def serialize_value(self, value: Any) -> float:
        return float(value)
    
    def deserialize_value(self, data: Any) -> float:
        return float(data)


@dataclass(frozen=True)
class MCPString(MCPPrimitive):
    def serialize_value(self, value: Any) -> str:
        return str(value)
    
    def deserialize_value(self, data: Any) -> str:
        return str(data)


@dataclass(frozen=True)
class MCPBool(MCPPrimitive):
    def serialize_value(self, value: Any) -> bool:
        return bool(value)
    
    def deserialize_value(self, data: Any) -> bool:
        return bool(data)


@dataclass(frozen=True)
class MCPArray(MCPType):
    items: MCPType
    
    def serialize_value(self, value: Any) -> list:
        if not isinstance(value, (list, tuple)):
            value = [value]
        return [self.items.serialize_value(item) for item in value]
    
    def deserialize_value(self, data: Any) -> list:
        if not isinstance(data, list):
            data = [data]
        return [self.items.deserialize_value(item) for item in data]


@dataclass(frozen=True)
class MCPObject(MCPType):
    properties: dict[str, MCPType]
    required: list[str]
    type_name: Optional[str] = None
    description: Optional[str] = None
    
    def serialize_value(self, value: Any) -> dict:
        result = {}
        
        if self.type_name:
            result["__mcp_type__"] = self.type_name
        
        if hasattr(value, '__dict__'):
            obj_dict = value.__dict__
        elif isinstance(value, dict):
            obj_dict = value
        else:
            obj_dict = {"value": value}
        
        for prop_name, prop_type in self.properties.items():
            if prop_name in obj_dict:
                result[prop_name] = prop_type.serialize_value(obj_dict[prop_name])
        
        return result
    
    def deserialize_value(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        if self.type_name and "__mcp_type__" in data:
            if data["__mcp_type__"] != self.type_name:
                raise ValueError(f"type mismatch: expected {self.type_name}, got {data['__mcp_type__']}")
        
        result = {}
        for prop_name, prop_type in self.properties.items():
            if prop_name in data:
                result[prop_name] = prop_type.deserialize_value(data[prop_name])
        
        return result


@dataclass(frozen=True)
class MCPUnion(MCPType):
    variants: tuple[MCPType, ...]
    
    def __post_init__(self):
        if len(self.variants) < 2:
            raise ValueError("union must have at least 2 variants")
    
    def serialize_value(self, value: Any) -> Any:
        for variant in self.variants:
            try:
                return variant.serialize_value(value)
            except (ValueError, TypeError, AttributeError):
                continue
        
        return str(value)
    
    def deserialize_value(self, data: Any) -> Any:
        if isinstance(data, dict) and "__mcp_type__" in data:
            type_name = data["__mcp_type__"]
            for variant in self.variants:
                if isinstance(variant, MCPObject) and variant.type_name == type_name:
                    return variant.deserialize_value(data)
        
        for variant in self.variants:
            try:
                return variant.deserialize_value(data)
            except (ValueError, TypeError, AttributeError):
                continue
        
        return data


@dataclass(frozen=True)
class MCPOptional(MCPType):
    inner_type: MCPType
    
    def serialize_value(self, value: Any) -> Any:
        if value is None:
            return None
        return self.inner_type.serialize_value(value)
    
    def deserialize_value(self, data: Any) -> Any:
        if data is None:
            return None
        return self.inner_type.deserialize_value(data)


MCP_INT = MCPInt()
MCP_FLOAT = MCPFloat()
MCP_STRING = MCPString()
MCP_BOOL = MCPBool() 