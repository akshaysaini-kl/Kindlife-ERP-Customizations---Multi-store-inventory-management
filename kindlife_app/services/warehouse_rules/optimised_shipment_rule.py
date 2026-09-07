import frappe
import logging
from typing import List, Dict, Optional
from .base_rule import BaseWarehouseRule

logger = logging.getLogger(__name__)

class OptmisedShipmentRule(BaseWarehouseRule):
    """
    Rule that optimizes for shipping cost and delivery time
    This rule may split orders across multiple warehouses if needed
    """
    
    def assign_warehouse(self, params=None) -> Optional[Dict]:
        """
        Find the optimal warehouse(s) for shipping the order
        
        Implementation:
        1. Calculate a score for each warehouse based on:
           - Distance to shipping address
           - Stock availability
           - Shipping cost
           - Delivery time
        2. Return the warehouse with the best score
        """
        try:
            # Check if we have coordinates
            if not self.coordinates:
                logger.warning("No coordinates provided for warehouse assignment")
                return self.fallback_warehouse
                
            # Extract latitude and longitude
            # The coordinates might be a tuple with more than 2 values (lat, lon, pincode)
            print(f"Coordinates type: {type(self.coordinates)}, value: {self.coordinates}")
            
            if isinstance(self.coordinates, tuple) and len(self.coordinates) >= 2:
                shipping_lat = float(self.coordinates[0])
                shipping_lon = float(self.coordinates[1])
                print(f"Extracted coordinates: lat={shipping_lat}, lon={shipping_lon}")
            else:
                logger.warning(f"Invalid coordinates format: {self.coordinates}")
                return self.fallback_warehouse
            
            # Get all warehouses with coordinates
            warehouses = frappe.get_all(
                "Warehouse",
                filters={
                    "latitude": ["is", "set"],
                    "longitude": ["is", "set"]
                },
                fields=["name", "latitude", "longitude"]
            )
            
            if not warehouses:
                logger.warning("No warehouses with coordinates found, using fallback warehouse")
                return self.fallback_warehouse
                
            # Get all item codes from the items list
            item_codes = [item.get('item_code') for item in self.items if item.get('item_code')]
            
            # Calculate scores for each warehouse
            warehouse_scores = []
            for warehouse_data in warehouses:
                try:
                    warehouse_name = warehouse_data.name
                    warehouse_lat = float(warehouse_data.latitude)
                    warehouse_lon = float(warehouse_data.longitude)
                    
                    # Calculate distance using Haversine formula
                    distance = self.warehouse_service._calculate_distance(
                        shipping_lat, shipping_lon, warehouse_lat, warehouse_lon
                    )
                    
                    # Calculate distance score (closer = higher score)
                    # Max score of 100 for warehouses within 5km, decreasing to 0 at 100km
                    distance_score = max(0, 100 - (distance / 1.0))
                    
                    # Calculate stock availability score
                    stock_score = 0
                    for item_code in item_codes:
                        stock_qty = self._get_stock_qty(warehouse_name, item_code)
                        if stock_qty > 0:
                            stock_score += 1
                    
                    # Normalize stock score (0-100)
                    if item_codes:
                        stock_score = (stock_score / len(item_codes)) * 100
                    
                    # Get TAT for this warehouse
                    tat = "1-2 days"  # Default TAT
                    priority = 1  # Default priority
                    try:
                        service_pincodes = frappe.get_all(
                            "Warehouse Servicable Pincode",
                            filters={"warehouse": warehouse_name},
                            fields=["tat", "priority"],
                            limit=1
                        )
                        if service_pincodes:
                            tat = service_pincodes[0].tat
                            priority = service_pincodes[0].priority or 1
                    except Exception as e:
                        logger.warning(f"Error getting TAT for warehouse {warehouse_name}: {e}")
                    
                    # Calculate priority score (higher priority = higher score)
                    priority_score = 100 - (int(priority) * 10)
                    
                    # Calculate TAT score (faster delivery = higher score)
                    tat_score = self._calculate_tat_score(tat)
                    
                    # Calculate final score (weighted average)
                    final_score = (distance_score * 0.4) + (stock_score * 0.3) + (priority_score * 0.2) + (tat_score * 0.1)
                    
                    warehouse_scores.append((warehouse_data, distance, tat, priority, final_score))
                except Exception as wh_e:
                    logger.warning(f"Error calculating score for warehouse {warehouse_data.name}: {wh_e}")
                    continue
            
            if not warehouse_scores:
                logger.warning("No warehouses with valid scores found")
                return self.fallback_warehouse
                
            # Sort by score (highest first)
            warehouse_scores.sort(key=lambda x: x[4], reverse=True)
            
            # Return the warehouse with the highest score
            warehouse_data, distance, tat, priority, score = warehouse_scores[0]
            
            # Get the full warehouse doc to access all fields
            warehouse = frappe.get_doc("Warehouse", warehouse_data.name)
            
            return {
                "warehouse_id": warehouse.name,
                "warehouse_code": warehouse.warehouse_code if hasattr(warehouse, 'warehouse_code') else warehouse.name,
                "warehouse_name": warehouse.warehouse_name if hasattr(warehouse, 'warehouse_name') else warehouse.name,
                "tat": tat,
                "priority": priority,
                "distance_km": round(distance, 2),
                "score": round(score, 2)
            }
            
        except Exception as e:
            logger.error(f"Error in OptmisedShipmentRule: {e}, using fallback warehouse")
            return self.fallback_warehouse
            
    def _get_stock_qty(self, warehouse: str, item_code: str) -> float:
        """Get the stock quantity of an item in a warehouse"""
        try:
            # Use frappe.db.get_value to get the actual_qty from bin
            stock_qty = frappe.db.get_value(
                "Bin",
                {"warehouse": warehouse, "item_code": item_code},
                "actual_qty"
            ) or 0
            return float(stock_qty)
        except Exception as e:
            logger.error(f"Error getting stock quantity: {e}")
            return 0
            
    def _calculate_tat_score(self, tat: str) -> float:
        """Calculate a score based on the TAT (Turn Around Time)"""
        try:
            # Parse TAT string (e.g., "1-2 days", "3-5 days", etc.)
            if not tat:
                return 50  # Default score for unknown TAT
                
            # Extract the first number from the TAT string
            import re
            numbers = re.findall(r'\d+', tat)
            if not numbers:
                return 50
                
            min_days = int(numbers[0])
            
            # Calculate score (faster delivery = higher score)
            if min_days <= 1:
                return 100  # Same day or next day delivery
            elif min_days <= 2:
                return 80  # 2-day delivery
            elif min_days <= 3:
                return 60  # 3-day delivery
            elif min_days <= 5:
                return 40  # 5-day delivery
            else:
                return 20  # More than 5 days
        except Exception as e:
            logger.error(f"Error calculating TAT score: {e}")
            return 50
