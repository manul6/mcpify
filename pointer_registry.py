import uuid
import weakref
from typing import Any, Dict, Optional, Set
import threading


class PointerRegistry:
    """manages live object instances with unique identifiers"""
    
    def __init__(self):
        self._objects: Dict[str, Any] = {}
        self._finalizers: Dict[str, weakref.finalize] = {}
        self._lock = threading.RLock()
    
    def register(self, obj: Any) -> str:
        """register an object and return its unique id"""
        obj_id = str(uuid.uuid4())
        
        with self._lock:
            self._objects[obj_id] = obj
            
            def cleanup(obj_id=obj_id):
                with self._lock:
                    self._objects.pop(obj_id, None)
                    self._finalizers.pop(obj_id, None)
            
            self._finalizers[obj_id] = weakref.finalize(obj, cleanup)
        
        return obj_id
    
    def get(self, obj_id: str) -> Optional[Any]:
        """retrieve object by id, returns none if not found"""
        with self._lock:
            return self._objects.get(obj_id)
    
    def unregister(self, obj_id: str) -> bool:
        """manually remove object from registry"""
        with self._lock:
            if obj_id in self._objects:
                del self._objects[obj_id]
                if obj_id in self._finalizers:
                    self._finalizers[obj_id].detach()
                    del self._finalizers[obj_id]
                return True
            return False
    
    def list_ids(self) -> Set[str]:
        """return all currently registered object ids"""
        with self._lock:
            return set(self._objects.keys())
    
    def size(self) -> int:
        """return number of registered objects"""
        with self._lock:
            return len(self._objects)
    
    def clear(self) -> None:
        """clear all registered objects"""
        with self._lock:
            for finalizer in self._finalizers.values():
                finalizer.detach()
            self._objects.clear()
            self._finalizers.clear()


_registry = PointerRegistry()

def register(obj: Any) -> str:
    """register an object and return its unique id"""
    return _registry.register(obj)

def get(obj_id: str) -> Optional[Any]:
    """retrieve object by id"""
    return _registry.get(obj_id)

def unregister(obj_id: str) -> bool:
    """manually remove object from registry"""
    return _registry.unregister(obj_id)

def list_ids() -> Set[str]:
    """return all currently registered object ids"""
    return _registry.list_ids()

def size() -> int:
    """return number of registered objects"""
    return _registry.size()

def clear() -> None:
    """clear all registered objects"""
    return _registry.clear() 