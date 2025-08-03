from typing import List, Dict, Optional, Union, Set

def add(a: int, b: int) -> int:
    """add two numbers"""
    return a + b

def greet(name: str) -> str:
    """greet someone"""
    return f"hello {name}!"

def multiply(x: int, y: int) -> int:
    """multiply two numbers"""
    return x * y

def process_list(items: List[str]) -> int:
    """count items in a list"""
    return len(items)

def merge_data(data: Dict[str, int]) -> str:
    """merge dictionary data into string"""
    return ", ".join(f"{k}:{v}" for k, v in data.items())

def optional_param(text: str, count: Optional[int] = None) -> str:
    """repeat text optionally"""
    if count is None:
        return text
    return text * count

def union_type(value: Union[int, str]) -> str:
    """handle int or string input"""
    return f"received: {value} (type: {type(value).__name__})"

def float_calc(x: float, y: float) -> float:
    """calculate with floats"""
    return x / y if y != 0 else 0.0

def bool_logic(flag: bool) -> str:
    """process boolean value"""
    return "enabled" if flag else "disabled"

class Calculator:
    """simple calculator class"""
    def __init__(self, initial: int = 0):
        self.value = initial
    
    def add_to_value(self, amount: int) -> int:
        """add amount to stored value"""
        self.value += amount
        return self.value
    
    @staticmethod
    def add_static(a: int, b: int) -> int:
        """add two numbers statically"""
        return a + b

class Person:
    """person with name and age"""
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def introduce(self) -> str:
        """introduce the person"""
        return f"hi, i'm {self.name} and i'm {self.age} years old"