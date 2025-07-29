from dataclasses import dataclass
from typing import Any, Optional, List
from mcp.types import Tool

from mcp_types import MCPType
from schema_builders import json_schema_builder


@dataclass(frozen=True)
class Parameter:
    name: str
    type: MCPType
    is_required: bool
    default_value: Optional[Any] = None
    description: Optional[str] = None
    is_positional: bool = False


@dataclass(frozen=True)
class FunctionSchema:
    name: str
    description: str
    parameters: List[Parameter]
    return_type: Optional[MCPType] = None
    
    def to_mcp_tool(self) -> Tool:
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = json_schema_builder.build(param.type)
            
            if param.description:
                properties[param.name]["description"] = param.description
            
            if param.is_required:
                required.append(param.name)
        
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": properties,
                "required": required
            }
        )
    
    @property
    def required_parameters(self) -> List[Parameter]:
        return [p for p in self.parameters if p.is_required]
    
    @property
    def optional_parameters(self) -> List[Parameter]:
        return [p for p in self.parameters if not p.is_required]
    
    @property
    def positional_parameters(self) -> List[Parameter]:
        return [p for p in self.parameters if p.is_positional] 