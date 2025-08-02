from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Union, Dict, Type
import json
import pointer_registry


class TypeRegistry:
    """global registry for storing and retrieving types by name"""
    _registry: Dict[str, Type] = {}
    
    @classmethod
    def register(cls, type_name: str, python_type: Type):
        """register a type by name"""
        cls._registry[type_name] = python_type
    
    @classmethod
    def get(cls, type_name: str) -> Optional[Type]:
        """get a type by name"""
        return cls._registry.get(type_name)
    
    @classmethod
    def clear(cls):
        """clear the registry (useful for testing)"""
        cls._registry.clear()


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
class MCPAny(MCPType):
    def serialize_value(self, value: Any) -> str:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return json.dumps(value)
        else:
            return json.dumps(value, default=str)
    
    def deserialize_value(self, data) -> Any:
        if isinstance(data, dict):
            parsed = data
        else:
            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return data
        
        if isinstance(parsed, dict) and "__mcp_ptr__" in parsed:
            obj_id = parsed.get("id")
            if obj_id:
                obj = pointer_registry.get(obj_id)
                if obj is not None:
                    return obj
                else:
                    raise ValueError(f"unknown object pointer: {obj_id}")
            else:
                raise ValueError("pointer envelope missing id")
        
        if isinstance(parsed, dict) and "__mcp_type__" in parsed:
            type_name = parsed["__mcp_type__"]
            python_type = TypeRegistry.get(type_name)
            if python_type:
                obj = python_type.__new__(python_type)
                for key, value in parsed.items():
                    if key != "__mcp_type__":
                        setattr(obj, key, value)
                return obj
            else:
                return parsed
        return parsed


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
    
    def serialize_value(self, value: Any) -> str:
        if not isinstance(value, (list, tuple)):
            value = [value]
        return json.dumps(value, default=str)
    
    def deserialize_value(self, data: str) -> list:
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, list):
                return [parsed]
            return parsed
        except (json.JSONDecodeError, TypeError):
            return [data]


@dataclass(frozen=True)
class MCPObject(MCPType):
    properties: dict[str, MCPType]
    required: list[str]
    type_name: Optional[str] = None
    description: Optional[str] = None
    
    def serialize_value(self, value: Any) -> str:
        if hasattr(value, '__dict__'):
            obj_dict = value.__dict__.copy()
            if self.type_name:
                obj_dict["__mcp_type__"] = self.type_name
            return json.dumps(obj_dict, default=str)
        elif isinstance(value, dict):
            obj_dict = value.copy()
            if self.type_name:
                obj_dict["__mcp_type__"] = self.type_name
            return json.dumps(obj_dict, default=str)
        else:
            return json.dumps({"value": value, "__mcp_type__": self.type_name or "object"}, default=str)
    
    def deserialize_value(self, data) -> Any:
        if isinstance(data, dict):
            parsed = data
        else:
            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return {"value": data}
        
        if isinstance(parsed, dict) and "__mcp_ptr__" in parsed:
            obj_id = parsed.get("id")
            if obj_id:
                obj = pointer_registry.get(obj_id)
                if obj is not None:
                    return obj
                else:
                    raise ValueError(f"unknown object pointer: {obj_id}")
            else:
                raise ValueError("pointer envelope missing id")
        
        if isinstance(parsed, dict) and "__mcp_type__" in parsed:
            type_name = parsed["__mcp_type__"]
            python_type = TypeRegistry.get(type_name)
            if python_type:
                obj = python_type.__new__(python_type)
                for key, value in parsed.items():
                    if key != "__mcp_type__":
                        setattr(obj, key, value)
                return obj
            else:
                return parsed
        elif isinstance(parsed, dict):
            return parsed
        else:
            return {"value": parsed}


@dataclass(frozen=True)
class MCPUnion(MCPType):
    variants: tuple[MCPType, ...]
    
    def __post_init__(self):
        if len(self.variants) < 2:
            raise ValueError("union must have at least 2 variants")
    
    def serialize_value(self, value: Any) -> str:
        return json.dumps(value, default=str)
    
    def deserialize_value(self, data: str) -> Any:
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data


@dataclass(frozen=True)
class MCPOptional(MCPType):
    inner_type: MCPType
    
    def serialize_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(self.inner_type, (MCPAny, MCPArray, MCPObject, MCPUnion)):
            return self.inner_type.serialize_value(value)
        return self.inner_type.serialize_value(value)
    
    def deserialize_value(self, data: Any) -> Any:
        if data is None:
            return None
        if isinstance(self.inner_type, (MCPAny, MCPArray, MCPObject, MCPUnion)):
            return self.inner_type.deserialize_value(data)
        return self.inner_type.deserialize_value(data)


MCP_ANY = MCPAny()
MCP_INT = MCPInt()
MCP_FLOAT = MCPFloat()
MCP_STRING = MCPString()
MCP_BOOL = MCPBool() 