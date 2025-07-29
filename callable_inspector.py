import inspect
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, get_origin, get_args, Union

from mcp_types import MCPType, MCPInt, MCPFloat, MCPString, MCPBool, MCPArray, MCPObject, MCPUnion, MCP_INT, MCP_FLOAT, MCP_STRING, MCP_BOOL
from function_schema import Parameter, FunctionSchema


class TypeConverter:
    def convert(self, annotation) -> MCPType:
        if annotation is int:
            return MCP_INT
        elif annotation is float:
            return MCP_FLOAT
        elif annotation is str:
            return MCP_STRING
        elif annotation is bool:
            return MCP_BOOL
        
        origin = get_origin(annotation)
        args = get_args(annotation)
        
        if origin is list:
            item_type = self.convert(args[0]) if args else MCP_STRING
            return MCPArray(items=item_type)
        elif origin is dict:
            return MCPObject(properties={}, required=[], description="dictionary object")
        elif origin is Union:
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return self.convert(non_none_args[0])
            else:
                variants = tuple(self.convert(arg) for arg in non_none_args)
                return MCPUnion(variants=variants)
        
        if inspect.isclass(annotation):
            return self._convert_class(annotation)
        
        return MCP_STRING
    
    def convert_from_value(self, value) -> MCPType:
        """convert a runtime value to its corresponding mcptype - used by value serializer"""
        if isinstance(value, int):
            return MCP_INT
        elif isinstance(value, float):
            return MCP_FLOAT
        elif isinstance(value, str):
            return MCP_STRING
        elif isinstance(value, bool):
            return MCP_BOOL
        elif isinstance(value, (list, tuple)):
            if not value:
                return MCPArray(items=MCP_STRING)
            item_type = self.convert_from_value(value[0])
            return MCPArray(items=item_type)
        elif isinstance(value, dict):
            return MCPObject(
                properties={k: self.convert_from_value(v) for k, v in value.items()},
                required=list(value.keys())
            )
        elif hasattr(value, '__dict__'):
            return self._convert_object_from_value(value)
        else:
            return MCP_STRING
    
    def _convert_object_from_value(self, obj) -> MCPObject:
        """convert a runtime object to mcpobject"""
        obj_dict = obj.__dict__
        properties = {}
        required = []
        
        for attr_name, attr_value in obj_dict.items():
            properties[attr_name] = self.convert_from_value(attr_value)
            required.append(attr_name)
        
        return MCPObject(
            properties=properties,
            required=required,
            type_name=type(obj).__name__
        )
    
    def _convert_class(self, cls: type) -> MCPObject:
        try:
            sig = inspect.signature(cls.__init__)
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                if param.annotation != inspect.Parameter.empty:
                    properties[param_name] = self.convert(param.annotation)
                else:
                    properties[param_name] = MCP_STRING
                
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
            
            return MCPObject(
                properties=properties,
                required=required,
                type_name=cls.__name__,
                description=cls.__doc__
            )
        except (ValueError, TypeError):
            return MCPObject(
                properties={},
                required=[],
                type_name=cls.__name__,
                description=cls.__doc__ or f"{cls.__name__} object"
            )


class ParameterExtractor(ABC):
    @abstractmethod
    def can_handle(self, func: Callable) -> bool:
        pass
    
    @abstractmethod
    def extract_parameters(self, func: Callable, type_converter: TypeConverter) -> List[Parameter]:
        pass
    
    def _extract_from_signature(self, sig: inspect.Signature, type_converter: TypeConverter) -> List[Parameter]:
        """common parameter extraction logic used by multiple extractors"""
        parameters = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            param_type = type_converter.convert(param.annotation) if param.annotation != inspect.Parameter.empty else MCP_STRING
            is_required = param.default == inspect.Parameter.empty
            default_value = param.default if param.default != inspect.Parameter.empty else None
            
            parameters.append(Parameter(
                name=param_name,
                type=param_type,
                is_required=is_required,
                default_value=default_value
            ))
        
        return parameters


class SignatureExtractor(ParameterExtractor):
    def can_handle(self, func: Callable) -> bool:
        try:
            inspect.signature(func)
            return True
        except (ValueError, TypeError):
            return False
    
    def extract_parameters(self, func: Callable, type_converter: TypeConverter) -> List[Parameter]:
        sig = inspect.signature(func)
        return self._extract_from_signature(sig, type_converter)


class ClassExtractor(ParameterExtractor):
    def can_handle(self, func: Callable) -> bool:
        if not inspect.isclass(func):
            return False
        try:
            inspect.signature(func.__init__)
            return True
        except (ValueError, TypeError):
            return False
    
    def extract_parameters(self, func: Callable, type_converter: TypeConverter) -> List[Parameter]:
        sig = inspect.signature(func.__init__)
        return self._extract_from_signature(sig, type_converter)


class BoundMethodExtractor(ParameterExtractor):
    def can_handle(self, func: Callable) -> bool:
        if not (hasattr(func, '__self__') and hasattr(func, '__func__')):
            return False
        try:
            inspect.signature(func.__func__)
            return True
        except (ValueError, TypeError):
            return False
    
    def extract_parameters(self, func: Callable, type_converter: TypeConverter) -> List[Parameter]:
        sig = inspect.signature(func.__func__)
        return self._extract_from_signature(sig, type_converter)


class BuiltinExtractor(ParameterExtractor):
    BUILTIN_SCHEMAS = {
        'getattr': [
            Parameter('obj', MCP_STRING, True, description='object to get attribute from'),
            Parameter('name', MCP_STRING, True, description='attribute name'),
            Parameter('default', MCP_STRING, False, description='default value if attribute not found')
        ],
        'setattr': [
            Parameter('obj', MCP_STRING, True, description='object to set attribute on'),
            Parameter('name', MCP_STRING, True, description='attribute name'),
            Parameter('value', MCP_STRING, True, description='value to set')
        ]
    }
    
    def can_handle(self, func: Callable) -> bool:
        name = getattr(func, '__name__', '')
        return name in self.BUILTIN_SCHEMAS
    
    def extract_parameters(self, func: Callable, type_converter: TypeConverter) -> List[Parameter]:
        name = getattr(func, '__name__', '')
        return self.BUILTIN_SCHEMAS.get(name, [])


class CallableInspector:
    def __init__(self):
        self.type_converter = TypeConverter()
        self.extractors = [
            SignatureExtractor(),
            ClassExtractor(),
            BoundMethodExtractor(),
            BuiltinExtractor()
        ]
    
    def inspect_callable(self, func: Callable) -> FunctionSchema:
        name = getattr(func, '__name__', str(func))
        description = getattr(func, '__doc__', None) or f"call {name}"
        
        parameters = []
        for extractor in self.extractors:
            if extractor.can_handle(func):
                parameters = extractor.extract_parameters(func, self.type_converter)
                break
        
        return FunctionSchema(
            name=name,
            description=description,
            parameters=parameters
        )


callable_inspector = CallableInspector() 