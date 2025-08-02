import inspect
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, get_origin, get_args, Union

from mcp_types import MCPType, MCPInt, MCPFloat, MCPString, MCPBool, MCPArray, MCPObject, MCPUnion, MCPAny, MCP_INT, MCP_FLOAT, MCP_STRING, MCP_BOOL, MCP_ANY
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
        
        return MCP_ANY
    
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
            return MCP_ANY
    
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
                    properties[param_name] = MCP_ANY
                
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
    
    def _extract_from_signature(self, sig: inspect.Signature, type_converter: TypeConverter, skip_self: bool = True) -> List[Parameter]:
        """common parameter extraction logic used by multiple extractors"""
        parameters = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self' and skip_self:
                continue
            
            param_type = type_converter.convert(param.annotation) if param.annotation != inspect.Parameter.empty else MCP_ANY
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


class UnboundMethodExtractor(ParameterExtractor):
    def can_handle(self, func: Callable) -> bool:
        # check if it's an unbound method (function defined in a class but not bound to an instance)
        if not hasattr(func, '__qualname__'):
            return False
        
        # unbound methods have qualname like "ClassName.method_name"
        qualname_parts = func.__qualname__.split('.')
        if len(qualname_parts) < 2:
            return False
        
        # must not be a bound method (no __self__ attribute)
        if hasattr(func, '__self__'):
            return False
            
        try:
            sig = inspect.signature(func)
            # check if first parameter is named 'self'
            params = list(sig.parameters.keys())
            return len(params) > 0 and params[0] == 'self'
        except (ValueError, TypeError):
            return False
    
    def extract_parameters(self, func: Callable, type_converter: TypeConverter) -> List[Parameter]:
        sig = inspect.signature(func)
        # for unbound methods, don't skip self - it should be exposed as a parameter
        parameters = self._extract_from_signature(sig, type_converter, skip_self=False)
        
        # mark the self parameter as positional and add usage documentation
        for i, param in enumerate(parameters):
            if param.name == 'self':
                # add specific documentation for the self parameter
                self_description = f"instance of {func.__qualname__.split('.')[0]} class (must be passed in dict format)"
                
                parameters[i] = Parameter(
                    name=param.name,
                    type=param.type,
                    is_required=param.is_required,
                    default_value=param.default_value,
                    description=self_description,
                    is_positional=True
                )
                break
        
        return parameters


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
        return self._extract_from_signature(sig, type_converter, skip_self=True)


class BuiltinExtractor(ParameterExtractor):
    BUILTIN_SCHEMAS = {
        'getattr': [
            Parameter('obj', MCP_ANY, True, description='object to get attribute from', is_positional=True),
            Parameter('name', MCP_STRING, True, description='attribute name', is_positional=True),
            Parameter('default', MCP_ANY, False, description='default value if attribute not found', is_positional=True)
        ],
        'setattr': [
            Parameter('obj', MCP_ANY, True, description='object to set attribute on', is_positional=True),
            Parameter('name', MCP_STRING, True, description='attribute name', is_positional=True),
            Parameter('value', MCP_ANY, True, description='value to set', is_positional=True)
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
            BuiltinExtractor(),
            UnboundMethodExtractor(),
            BoundMethodExtractor(),
            ClassExtractor(),
            SignatureExtractor()
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