import frappe
import logging
import sys
from typing import List, Dict, Optional, Any
from kindlife_app.api.inventory import get_item_warehouse_inventory
from kindlife_app.api.sales_order import get_address
from .base_rule import BaseWarehouseRule

logger = logging.getLogger(__name__)

class ClosestFulfillAllRule(BaseWarehouseRule):
    """
    Rule that assigns warehouses to items based on proximity and stock availability
    Each item is assigned to the closest warehouse that has sufficient stock
    """
    
    def assign_warehouse(self, params=None) -> List[Dict[str, Any]]:
        """
        Find the best warehouse for each item in the order based on proximity and stock availability
        
        Implementation:
        1. Calculate distance to each warehouse using coordinates
        2. Sort warehouses by distance (closest first)
        3. For each item, find the closest warehouse with sufficient stock
        4. Return an array of objects with item_code and warehouse details
        5. If no warehouse has sufficient stock for an item, assign it to the fallback warehouse
        """
        try:
            # Initialize result list to store item-warehouse assignments
            result = []
            
            # Check if we have coordinates
            if not self.coordinates:
                logger.warning("No coordinates provided for warehouse assignment")
                # Assign all items to fallback warehouse
                return self._assign_all_to_fallback()
                
            # Extract latitude and longitude
            # The coordinates might be a tuple with more than 2 values (lat, lon, pincode)
            print(f"Coordinates type: {type(self.coordinates)}, value: {self.coordinates}")
            
            if isinstance(self.coordinates, tuple) and len(self.coordinates) >= 2:
                shipping_lat = float(self.coordinates[0])
                shipping_lon = float(self.coordinates[1])
                print(f"Extracted coordinates: lat={shipping_lat}, lon={shipping_lon}")
            else:
                logger.warning(f"Invalid coordinates format: {self.coordinates}")
                return self._assign_all_to_fallback()
            
            # Get all warehouses with coordinates
            warehouses = frappe.get_all(
                "Warehouse",
                filters={
                    "custom_type": "B2C",
                    "disabled": 0,
                    "custom_main_warehouse": 1
                },
                fields=["name", "disabled", "custom_latitude", "custom_longitude"]
            )
           
            print(f"Found {len(warehouses)} warehouses with coordinates")
            
            for i, wh in enumerate(warehouses[:5]):  # Print first 5 warehouses
                print(f"  Warehouse {i+1}: {wh.name}, Lat: {wh.custom_latitude}, Lon: {wh.custom_longitude}, status: {wh.disabled}")
            if len(warehouses) > 5:
                print(f"  ... and {len(warehouses) - 5} more warehouses")
                
            if not warehouses:
                logger.warning("No warehouses with coordinates found, using fallback warehouse")
                return self._assign_all_to_fallback()
            
            # Calculate distance to each warehouse and create sorted list
            warehouse_distances = []
            for warehouse_data in warehouses:
                try:
                    warehouse_name = warehouse_data.name
                    warehouse_lat = float(warehouse_data.custom_latitude) if warehouse_data.custom_latitude else 0
                    warehouse_lon = float(warehouse_data.custom_longitude) if warehouse_data.custom_longitude else 0
                    
                    if warehouse_lat == 0 or warehouse_lon == 0:
                        logger.warning(f"Warehouse {warehouse_name} has invalid coordinates: ({warehouse_lat}, {warehouse_lon})")
                        continue
                    
                    # Calculate distance using Haversine formula
                    distance = self.warehouse_service._calculate_distance(
                        shipping_lat, shipping_lon, warehouse_lat, warehouse_lon
                    )
                    
                    # Get the TAT for this warehouse
                    tat = "1-2 days"  # Default TAT
                    try:
                        service_pincodes = frappe.get_all(
                            "Warehouse Servicable Pincode",
                            filters={"warehouse": warehouse_name},
                            fields=["tat"],
                            limit=1
                        )
                        if service_pincodes:
                            tat = service_pincodes[0].tat
                    except Exception as e:
                        logger.warning(f"Error getting TAT for warehouse {warehouse_name}: {e}")
                    
                    # Format warehouse address
                    address = get_address("Warehouse",warehouse_name)
                    
                    # Create warehouse info object with distance and address
                    warehouse_info = {
                        "warehouse_id": warehouse_name,
                        "warehouse_name": warehouse_data.warehouse_name if hasattr(warehouse_data, 'warehouse_name') else warehouse_name,
                        "distance_km": round(distance, 2),
                        "warehouse_address": address
                    }
                    
                    warehouse_distances.append((warehouse_name, distance, warehouse_info))
                    print(f"Warehouse {warehouse_name} at {distance:.2f} km")
                    
                except Exception as e:
                    logger.warning(f"Error processing warehouse {warehouse_data.name}: {e}")
                    print(f"  Error: {e}")
                    continue
            
            if not warehouse_distances:
                logger.warning("No warehouses with valid distances found")
                return self._assign_all_to_fallback()
            
            # Sort warehouses by distance (closest first)
            warehouse_distances.sort(key=lambda x: x[1])
            print(f"Sorted {len(warehouse_distances)} warehouses by distance")
            
            # Process each item and find the best warehouse
            result = []
            for item in self.items:
                item_code = item.get('item_code')
                qty_required = float(item.get('qty', 1))
                
                if not item_code:
                    logger.warning(f"Item without item_code found: {item}")
                    continue
                    
                print(f"\nProcessing item: {item_code}, qty: {qty_required}")
                
                # Find the closest warehouse with sufficient stock
                assigned_warehouse = None
                for warehouse_name, distance, warehouse_info in warehouse_distances:
                    stock_qty = self._get_stock_qty(warehouse_name, item_code)
                    print(f"  Checking warehouse {warehouse_name}: {stock_qty} units available")
                    
                    if stock_qty >= qty_required:
                        assigned_warehouse = warehouse_info
                        print(f"  Assigned to warehouse {warehouse_name} with {stock_qty} units")
                        break
                
                # If no warehouse has sufficient stock, use fallback warehouse
                if not assigned_warehouse:
                    print(f"  No warehouse with sufficient stock for {item_code}, using fallback")
                    fallback = self._get_fallback_warehouse_info()
                    assigned_warehouse = fallback
                    assigned_warehouse["error"] = f"No warehouse with sufficient stock for {item_code}"
                
                # Add item-warehouse assignment to result
                item_result = {
                    "item_code": item_code,
                    "qty": qty_required,
                    **assigned_warehouse
                }
                result.append(item_result)
            
            print("\n==== Final Result ====")
            print(f"Assigned {len(result)} items to warehouses")
            for item_assignment in result:
                print(f"Item {item_assignment['item_code']} -> Warehouse {item_assignment['warehouse_id']}")
            print("=====================\n")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in ClosestFulfillAllRule: {e}, using fallback warehouse")
            return self._assign_all_to_fallback()
            
    def _get_stock_qty(self, warehouse: str, item_code: str) -> float:
        """Get the stock quantity of an item in a warehouse"""
        try:
            item_inventory_warehouse_wise = get_item_warehouse_inventory(item_code, warehouse)
            # Use frappe.db.get_value to get the actual_qty from bin
            stock_qty = item_inventory_warehouse_wise.get("actual_qty")
            return float(stock_qty) if stock_qty is not None else 0
        except Exception as e:
            logger.error(f"Error getting stock quantity: {e}")
            return 0
            
    
    def _get_fallback_warehouse_info(self) -> Dict:
        """Get information about the fallback warehouse"""
        try:
            fallback = self.fallback_warehouse
            if not fallback:
                logger.warning("No fallback warehouse defined, using empty values")
                return {
                    "warehouse_id": "",
                    "warehouse_name": "Fallback Warehouse",
                    "distance_km": 0,
                    "address": "Address not available"
                }
                
            # Get the full warehouse doc to access all fields
            warehouse_id = fallback.get("warehouse_id", "")
            if warehouse_id:
                try:
                    warehouse = frappe.get_doc("Warehouse", warehouse_id)
                    return {
                        "warehouse_id": warehouse.name,
                        "warehouse_name": warehouse.warehouse_name if hasattr(warehouse, 'warehouse_name') else warehouse.name,
                        "distance_km": 0,
                        "address": get_address("Warehouse",warehouse.name)
                    }
                except Exception as e:
                    logger.error(f"Error getting fallback warehouse details: {e}")
            
            # If we couldn't get the warehouse details, return default values
            return {
                "warehouse_id": warehouse_id or "",
                "warehouse_name": fallback.get("warehouse_name", "Fallback Warehouse"),
                "distance_km": 0,
                "address": "Address not available"
            }
        except Exception as e:
            logger.error(f"Error in _get_fallback_warehouse_info: {e}")
            return {
                "warehouse_id": "",
                "warehouse_name": "Fallback Warehouse",
                "distance_km": 0,
                "address": "Address not available"
            }
    
    def _assign_all_to_fallback(self) -> List[Dict]:
        """Assign all items to the fallback warehouse"""
        fallback_info = self._get_fallback_warehouse_info()
        result = []
        
        for item in self.items:
            item_code = item.get('item_code')
            qty = float(item.get('qty', 1))
            
            if not item_code:
                continue
                
            item_result = {
                "item_code": item_code,
                "qty": qty,
                **fallback_info,
                "error": "Using fallback warehouse due to error or missing data"
            }
            result.append(item_result)
            
        return result
