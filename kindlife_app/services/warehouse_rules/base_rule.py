from abc import ABC, abstractmethod
import pprint

from typing import List, Dict, Optional

class BaseWarehouseRule(ABC):
    """
    Base class for warehouse assignment rules
    All warehouse assignment rules should inherit from this class
    """
    
    def __init__(self, warehouse_service, params):
        """
        Initialize the rule with warehouse service and params object
        
        Args:
            warehouse_service: The warehouse service instance
            params: Dictionary containing:
                - items: List of items to be shipped
                - coordinates: Tuple of (latitude, longitude) for the shipping address
        """
        self.warehouse_service = warehouse_service
        self.params = params
        
        # Extract coordinates from params
        self.coordinates = params.get('coordinates')
        self.items = params.get('items', [])
        
        # Get the fallback warehouse from warehouse service
        self.fallback_warehouse = None
        self.fallback_warehouse =  warehouse_service._get_default_warehouse()

    def debug_print(obj, title=None):
        print("\n" + "="*50)
        if title:
            print(f"DEBUG: {title}")
        
        print(f"Type: {type(obj)}")
        
        if hasattr(obj, 'as_dict') and callable(getattr(obj, 'as_dict')):
            print("Object as dict:")
            pprint.pprint(obj.as_dict())
        elif hasattr(obj, '__dict__'):
            print("Object attributes:")
            pprint.pprint(obj.__dict__)
        else:
            print("Object value:")
            pprint.pprint(obj)
        
        print("="*50 + "\n")
        
    @abstractmethod
    def assign_warehouse(self, params) -> Optional[Dict]:
        """
        Assign a warehouse based on the rule's logic using the params object
        
        Args:
            params: Dictionary containing all shipping parameters
            
        Returns:
            Dictionary with warehouse details or None if no warehouse could be assigned
        """
        pass

    