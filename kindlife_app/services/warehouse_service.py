import frappe
from frappe import _
import logging
from typing import List, Optional, Dict, Tuple
from .geocoding_service import GeocodingService
import os

logger = logging.getLogger(__name__)

class WarehouseService:
    """
    Service for warehouse assignment and management
    Adapted from KindlifeLogisticServices for Frappe
    """
    
    def __init__(self):
        """Initialize warehouse service"""
        self.geocoding_service = GeocodingService()
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2) -> float:
        """
        Calculate the Haversine distance between two points in kilometers
        """
        from math import radians, cos, sin, asin, sqrt
        
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371  # Radius of earth in kilometers
        return c * r
    
    def _find_warehouse_by_proximity(
        self, 
        items: List[Dict], 
        shipping_address_line1: str = None, 
        shipping_address_line2: str = None, 
        shipping_city: str = None, 
        shipping_state: str = None, 
        shipping_pincode: str = None, 
        shipping_country: str = None, 
        shipping_rule = None
    ) -> Optional[Dict]:
        """
        Find the closest warehouse to the shipping coordinates
        """
        try:
            # Check if shipping_rule is a class instance with assign_warehouse method
            if shipping_rule and hasattr(shipping_rule, 'assign_warehouse'):
                # Use the rule class to assign warehouse
                logger.info(f"Using rule class {shipping_rule.__class__.__name__} to assign warehouse")
                # Pass the params object to the assign_warehouse method
                # This is redundant since we already passed it during instantiation, but it's for compatibility
                params = {"items": items}
                return shipping_rule.assign_warehouse(params)
            
            # If shipping_rule is not a class instance, proceed with the default proximity-based logic
            # This is a fallback and should not normally be reached
            logger.warning("No valid shipping rule instance provided, using default proximity logic")
            return self._get_default_warehouse()
            
            if not shipping_lat or not shipping_lon:
                logger.warning(f"Missing coordinates for shipping pincode {shipping_pincode}")
                return None
            
            # Get all serviceable warehouses for this pincode
            try:
                serviceable_warehouses = frappe.get_all(
                    "Warehouse Servicable Pincode",
                    filters={"pincode": shipping_pincode},
                    fields=["warehouse", "tat", "priority"]
                )
                
                if not serviceable_warehouses:
                    logger.warning(f"No warehouses service pincode {shipping_pincode}")
                    return None
            except Exception as e:
                logger.warning(f"Error getting serviceable warehouses: {e}")
                return None
                    
            # Calculate distance to each warehouse
            warehouse_distances = []
            for service_pincode in serviceable_warehouses:
                try:
                    warehouse = frappe.get_doc("Warehouse", service_pincode.warehouse)
                    
                    # Skip warehouses without coordinates
                    if not warehouse.latitude or not warehouse.longitude:
                        continue
                    
                    # Calculate distance
                    distance = self._calculate_distance(
                        shipping_lat,
                        shipping_lon,
                        float(warehouse.latitude),
                        float(warehouse.longitude)
                    )
                    
                    warehouse_distances.append((warehouse, service_pincode, distance))
                except Exception as e:
                    logger.warning(f"Error calculating distance for warehouse {service_pincode.warehouse}: {e}")
                    continue
            
            if not warehouse_distances:
                logger.warning(f"No warehouses with coordinates service pincode {shipping_pincode}")
                return None
            
            # Sort by distance
            warehouse_distances.sort(key=lambda x: x[2])
            
            # Return the closest warehouse
            closest_warehouse, service_pincode, distance = warehouse_distances[0]
            
            return {
                "warehouse_id": closest_warehouse.name,
                "warehouse_code": closest_warehouse.warehouse_code if hasattr(closest_warehouse, 'warehouse_code') else closest_warehouse.name,
                "warehouse_name": closest_warehouse.warehouse_name,
                "tat": service_pincode.tat,
                "distance_km": round(distance, 2)
            }
            
        except Exception as e:
            logger.error(f"Error finding warehouse by proximity: {e}")
            return None
    
    def __init__(self):
        # Initialize instance variables
        self.fallback_warehouse = None
        
    def _get_warehouse_rule(self, rule_name, params):
        """
        Factory function to get a warehouse rule instance by name and pass the params object
        Halts execution if the rule doesn't exist
        
        Args:
            rule_name: Name of the rule class
            params: Dictionary containing all shipping parameters:
                - items: List of items to be shipped
                - shipping_address_line1: First line of shipping address
                - shipping_address_line2: Second line of shipping address (optional)
                - shipping_city: City for shipping (optional)
                - shipping_state: State for shipping (optional)
                - shipping_pincode: Pincode for shipping (optional)
                - shipping_country: Country for shipping (optional)
        """
        try:
            # Use a dictionary to map rule names to their import paths
            rule_map = {
                "ClosestFulfillAllRule": "kindlife_app.services.warehouse_rules.closest_fulfill_all_rule",
                "OptmisedShipmentRule": "kindlife_app.services.warehouse_rules.optimised_shipment_rule"
                # Add more rules here as needed
            }
            
            # Check if the rule exists in our map
            if rule_name not in rule_map:
                error_msg = f"Unknown warehouse rule: {rule_name}. Valid rules are: {', '.join(rule_map.keys())}"
                logger.error(error_msg)
                frappe.throw(error_msg)
            
            # Import the module and get the class
            module_name = rule_map[rule_name]
            
            # Try to import the module and instantiate the class
            try:
                module = __import__(module_name, fromlist=[rule_name])
                rule_class = getattr(module, rule_name)
                
                # Return an instance of the class with the params object
                instance = rule_class(self, params)
                logger.info(f"Successfully instantiated warehouse rule: {rule_name} with params object")
                return instance
            except ImportError:
                error_msg = f"Rule module not found: {module_name}"
                logger.error(error_msg)
                frappe.throw(error_msg)
            except AttributeError:
                error_msg = f"Rule class {rule_name} not found in module {module_name}"
                logger.error(error_msg)
                frappe.throw(error_msg)
            except TypeError as te:
                error_msg = f"Error instantiating rule class {rule_name}: {te}. Check if the constructor accepts all parameters."
                logger.error(error_msg)
                frappe.throw(error_msg)
        except Exception as e:
            error_msg = f"Error creating warehouse rule {rule_name}: {e}"
            logger.error(error_msg)
            frappe.throw(error_msg)
        
    def _get_default_warehouse(self) -> Optional[Dict]:
        """
        Get the default warehouse for when proximity-based assignment fails
        """
        try:
            # First check if we already have a fallback warehouse from earlier
            if hasattr(self, 'fallback_warehouse') and self.fallback_warehouse:
                default_warehouse_name = self.fallback_warehouse
                logger.info(f"Using previously loaded fallback warehouse: {default_warehouse_name}")
            else:
                # Get default warehouse from Warehouse Service Settings
                try:
                    settings = frappe.get_single("Warehouse Service Settings")
                    if settings and settings.fallback_warehouse:
                        default_warehouse_name = settings.fallback_warehouse
                        # Store for future use
                        self.fallback_warehouse = default_warehouse_name
                        logger.info(f"Using fallback warehouse from settings: {default_warehouse_name}")
                    else:
                        # Fallback to environment variable if settings not found or incomplete
                        DEFAULT_WAREHOUSE_CODE = os.getenv("DEFAULT_WAREHOUSE_CODE")
                        if not DEFAULT_WAREHOUSE_CODE:
                            logger.error("No default warehouse configured in settings or environment")
                            return None
                        
                        # Find warehouse by code
                        warehouses = frappe.get_all(
                            "Warehouse",
                            filters={"warehouse_code": DEFAULT_WAREHOUSE_CODE},
                            fields=["name"]
                        )
                        
                        if not warehouses:
                            logger.error(f"Default warehouse with code {DEFAULT_WAREHOUSE_CODE} not found")
                            return None
                        
                        default_warehouse_name = warehouses[0].name
                except Exception as e:
                    logger.warning(f"Error getting settings for default warehouse: {e}")
                    # Fallback to any warehouse
                    warehouses = frappe.get_all("Warehouse", fields=["name"], limit=1)
                    if not warehouses:
                        logger.error("No warehouses found in the system")
                        return None
                    default_warehouse_name = warehouses[0].name
                    logger.info(f"Using first available warehouse as fallback: {default_warehouse_name}")
            
            # Get warehouse details
            warehouse = frappe.get_doc("Warehouse", default_warehouse_name)
            
            # Get the first service pincode for this warehouse (for TAT)
            service_pincodes = frappe.get_all(
                "Warehouse Servicable Pincode",
                filters={"warehouse": warehouse.name},
                fields=["tat"],
                limit=1
            )
            
            tat = "1-2 days"  # Default TAT
            if service_pincodes:
                tat = service_pincodes[0].tat
            
            return {
                "warehouse_id": warehouse.name,
                "warehouse_code": warehouse.warehouse_code if hasattr(warehouse, 'warehouse_code') else warehouse.name,
                "latitude": warehouse.custom_latitude,
                "longitude": warehouse.custom_longitude
            }
            
        except Exception as e:
            logger.error(f"Error getting default warehouse: {e}")
            return None
    
    def find_the_shipping_warehouses(
        self, 
        items: List[Dict],
        shipping_address_line1: str,
        shipping_address_line2: str = None,
        shipping_city: str = None,
        shipping_state: str = None,
        shipping_pincode: str = None,
        shipping_country: str = "India",
        shipping_rule: str = None
    ) -> Optional[Dict]:
        """
        Find the best warehouse for an order based on proximity to shipping address
        Falls back to default warehouse if proximity calculation fails
        """
        
        # First geocode the shipping address to get coordinates
        print("\n==== find_the_shipping_warehouses Debug Info ====")
        print(f"Shipping address: {shipping_address_line1}, {shipping_city}, {shipping_state}, {shipping_pincode}")
        
        geocoding_service = GeocodingService()
        coords = geocoding_service.geocode_address_with_cache(
            shipping_address_line1, shipping_address_line2, shipping_city, 
            shipping_state, shipping_pincode, shipping_country
        )
        
        print(f"Geocoded coordinates: {coords}")
        if coords:
            print(f"Coordinates type: {type(coords)}")
            print(f"Coordinates length: {len(coords) if isinstance(coords, tuple) else 'N/A'}")
            if isinstance(coords, tuple) and len(coords) >= 2:
                print(f"Latitude: {coords[0]}, Longitude: {coords[1]}")
                if len(coords) > 2:
                    print(f"Additional data: {coords[2:]}")
        print("======================================\n")
        
        # Log the coordinates
        if coords:
            logger.info(f"Geocoded shipping address to coordinates: {coords}")
        else:
            logger.warning(f"Could not geocode shipping address: {shipping_address_line1}, {shipping_city}, {shipping_state}, {shipping_pincode}")
            # If geocoding fails, return the fallback warehouse directly
            return self._get_default_warehouse()
        
        # Create a params object with only items and coordinates
        params = {
            "items": items,
            "coordinates": coords
        }
       
        if not shipping_rule:
            # Default to a reasonable shipping rule if none is provided
            #shipping_rule = "ClosestFulfillAllRule"  # Default value
        
            try:
                # This is the correct way to access a single doctype
                settings = frappe.get_single("Warehouse Service Settings")
               
                if settings and settings.warehouse_assignment_rule:
                    # Get the class name from settings
                    rule_class_name = settings.warehouse_assignment_rule
                    
                    # Use the factory function to get the rule instance with the params object
                    rule_instance = self._get_warehouse_rule(rule_class_name, params)
                    
                    # Call assign_warehouse on the rule instance and return the result
                    print("\n==== Calling assign_warehouse on rule instance ====")
                    warehouse_assignment = rule_instance.assign_warehouse(params)
                    print(f"Warehouse assignment: {warehouse_assignment}")
                    print("============================================\n")
                    
                    return warehouse_assignment
                    
                # Also store the fallback warehouse for later use
                if settings and settings.fallback_warehouse:
                    self.fallback_warehouse = settings.fallback_warehouse
                    logger.info(f"Using fallback warehouse from settings: {self.fallback_warehouse}")
            except frappe.DoesNotExistError:
                logger.warning("Warehouse Service Settings record does not exist yet")
                # Create the settings if they don't exist
                try:
                    # Default to ClosestFulfillAllRule if no rule is specified
                    default_rule = "ClosestFulfillAllRule"
                    
                    # Try to find a default warehouse
                    default_warehouse = None
                    warehouses = frappe.get_all("Warehouse", fields=["name"], limit=1)
                    if warehouses:
                        default_warehouse = warehouses[0].name
                    
                    # Create new settings
                    new_settings = frappe.get_doc({
                        "doctype": "Warehouse Service Settings",
                        "warehouse_assignment_rule": default_rule,
                        "fallback_warehouse": default_warehouse
                    })
                    
                    new_settings.insert()
                    logger.info(f"Created new Warehouse Service Settings with rule: {default_rule}")
                    
                    # Try to instantiate the rule class
                    try:
                        # Use the factory function to get the rule instance with the params object
                        rule_instance = self._get_warehouse_rule(default_rule, params)
                        
                        # Call assign_warehouse on the rule instance and return the result
                        print("\n==== Calling assign_warehouse on default rule instance ====")
                        warehouse_assignment = rule_instance.assign_warehouse(params)
                        print(f"Warehouse assignment: {warehouse_assignment}")
                        print("=================================================\n")
                        
                        return warehouse_assignment
                    except Exception as rule_error:
                        logger.warning(f"Could not instantiate default rule: {rule_error}")
                        return self._get_default_warehouse()
                        
                    # Store the fallback warehouse
                    if default_warehouse:
                        self.fallback_warehouse = default_warehouse
                except Exception as create_error:
                    logger.warning(f"Could not create Warehouse Service Settings: {create_error}")
            except Exception as e:
                logger.warning(f"Error accessing Warehouse Service Settings: {e}")
                # Default to ClosestFulfillAllRule if all else fails
                default_rule = "ClosestFulfillAllRule"
                try:
                    # Use the factory function to get the rule instance with the params object
                    rule_instance = self._get_warehouse_rule(default_rule, params)
                    
                    # Call assign_warehouse on the rule instance and return the result
                    print("\n==== Calling assign_warehouse on fallback rule instance ====")
                    warehouse_assignment = rule_instance.assign_warehouse(params)
                    print(f"Warehouse assignment: {warehouse_assignment}")
                    print("===================================================\n")
                    
                    return warehouse_assignment
                except Exception as rule_error:
                    logger.warning(f"Could not instantiate fallback rule: {rule_error}")
                    return self._get_default_warehouse()

        # If we get here, something went wrong with all the rule instantiation attempts
        # Return the default warehouse as a last resort
        return self._get_default_warehouse()
    
    def find_closest_warehouse_for_location(self, customer_lat: float, customer_lon: float, shipping_pincode: str) -> Optional[Dict]:
        """
        Find the closest warehouse to a customer's exact lat/lon for quick commerce.

        This method first finds all warehouses that service the given pincode and then
        calculates the Haversine distance from the customer's coordinates to each of
        those warehouses, selecting the nearest one.
        """
        try:
            # Step 1: Find all warehouses that service the given pincode
            serviceable_warehouses = frappe.get_all(
                "Warehouse Servicable Pincode",
                filters={"pincode": shipping_pincode},
                fields=["warehouse", "tat"]
            )

            if not serviceable_warehouses:
                logger.warning(f"No warehouses service pincode {shipping_pincode}")
                return None

            # Step 2: Calculate distance from the customer to each serviceable warehouse
            warehouse_distances = []
            for service_pincode in serviceable_warehouses:
                warehouse = frappe.get_doc("Warehouse", service_pincode.warehouse)
                
                # Skip warehouses without coordinates
                if not warehouse.latitude or not warehouse.longitude:
                    continue
                
                distance = self._calculate_distance(
                    customer_lat,
                    customer_lon,
                    float(warehouse.latitude),
                    float(warehouse.longitude)
                )
                warehouse_distances.append((warehouse, service_pincode, distance))
            
            if not warehouse_distances:
                return None

            # Step 3: Sort by distance to find the closest
            warehouse_distances.sort(key=lambda x: x[2])
            closest_warehouse, service_pincode, distance = warehouse_distances[0]

            # Step 4: Return the details of the closest warehouse
            return {
                "warehouse_id": closest_warehouse.name,
                "warehouse_code": closest_warehouse.warehouse_code if hasattr(closest_warehouse, 'warehouse_code') else closest_warehouse.name,
                "warehouse_name": closest_warehouse.warehouse_name,
                "tat": service_pincode.tat,
                "distance_km": round(distance, 2)
            }
        
        except Exception as e:
            logger.error(f"Error finding warehouse by location: {e}")
            return None
    
    def find_qcommerce_warehouse(self, customer_lat: float, customer_lon: float, shipping_pincode: str) -> Optional[Dict]:
        """
        Public method to find the best warehouse for a quick commerce order.
        Falls back to the default warehouse if no specific warehouse is found.
        """
        warehouse_assignment = self.find_closest_warehouse_for_location(customer_lat, customer_lon, shipping_pincode)

        if not warehouse_assignment:
            logger.warning(f"Could not find q-commerce warehouse for {shipping_pincode} at ({customer_lat}, {customer_lon}). Falling back to default.")
            warehouse_assignment = self._get_default_warehouse()
            
        return warehouse_assignment
    
    def get_warehouses_for_pincode(self, pincode: str) -> List[Dict]:
        """Get all warehouses that service a specific pincode"""
        try:
            # Check if the doctype exists
            if not frappe.db.exists('DocType', 'Warehouse Servicable Pincode'):
                logger.warning("Warehouse Servicable Pincode doctype does not exist")
                # Return some default warehouses as fallback
                return self._get_fallback_warehouses()
                
            # Get all service pincodes for this pincode
            service_pincodes = frappe.get_all(
                "Warehouse Servicable Pincode",
                filters={"pincode": pincode},
                fields=["warehouse", "tat", "priority"]
            )
            
            if not service_pincodes:
                logger.info(f"No warehouses found for pincode {pincode}, returning all warehouses")
                # If no warehouses for this pincode, return all warehouses
                service_pincodes = frappe.get_all(
                    "Warehouse Servicable Pincode",
                    fields=["warehouse", "tat", "priority"],
                    limit=5
                )
                
                if not service_pincodes:
                    return self._get_fallback_warehouses()
            
            # Get warehouse details for each service pincode
            warehouses = []
            for sp in service_pincodes:
                try:
                    warehouse = frappe.get_doc("Warehouse", sp.warehouse)
                    warehouses.append({
                        "id": warehouse.name,
                        "name": warehouse.warehouse_name,
                        "priority": sp.priority or 1,
                        "tat": sp.tat or "1-2 days"
                    })
                except Exception as wh_e:
                    logger.warning(f"Error getting warehouse {sp.warehouse}: {wh_e}")
            
            # Sort by priority
            warehouses.sort(key=lambda x: x.get("priority", 1))
            
            return warehouses
            
        except Exception as e:
            logger.error(f"Error getting warehouses for pincode: {e}")
            return self._get_fallback_warehouses()
            
    def _get_fallback_warehouses(self) -> List[Dict]:
        """Get fallback warehouses when no specific ones are found"""
        try:
            # Try to get any warehouses from the system
            warehouses = frappe.get_all(
                "Warehouse",
                fields=["name", "warehouse_name"],
                limit=5
            )
            
            if not warehouses:
                return []
                
            result = []
            for wh in warehouses:
                result.append({
                    "id": wh.name,
                    "name": wh.warehouse_name if hasattr(wh, 'warehouse_name') else wh.name,
                    "priority": 1,
                    "tat": "1-2 days"
                })
                
            return result
        except Exception as e:
            logger.error(f"Error getting fallback warehouses: {e}")
            return []
    
    def get_warehouse_coverage(self, warehouse_id: str) -> List[str]:
        """Get all pincodes covered by a warehouse"""
        try:
            service_pincodes = frappe.get_all(
                "Warehouse Servicable Pincode",
                filters={"warehouse": warehouse_id},
                fields=["pincode"]
            )
            
            return [sp.pincode for sp in service_pincodes]
            
        except Exception as e:
            logger.error(f"Error getting warehouse coverage: {e}")
            return []
    
    def update_warehouse_coverage(self, warehouse_id: str, pincodes: List[str], tat: str = '1-2 days', priority: int = 1) -> bool:
        """Update the pincodes covered by a warehouse"""
        try:
            # Delete existing pincodes
            existing_pincodes = frappe.get_all(
                "Warehouse Servicable Pincode",
                filters={"warehouse": warehouse_id},
                fields=["name"]
            )
            
            for sp in existing_pincodes:
                frappe.delete_doc("Warehouse Servicable Pincode", sp.name)
            
            # Add new pincodes
            for pincode in pincodes:
                frappe.get_doc({
                    "doctype": "Warehouse Servicable Pincode",
                    "warehouse": warehouse_id,
                    "pincode": pincode,
                    "priority": priority,
                    "tat": tat
                }).insert()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating warehouse coverage: {e}")
            frappe.db.rollback()
            return False
    
    def get_warehouse_stats(self, warehouse_id: str) -> Dict:
        """Get statistics for a warehouse"""
        try:
            warehouse = frappe.get_doc("Warehouse", warehouse_id)
            if not warehouse:
                return {}
            
            pincode_count = frappe.db.count(
                "Warehouse Servicable Pincode",
                filters={"warehouse": warehouse_id}
            )
            
            return {
                "warehouse_code": warehouse.warehouse_code if hasattr(warehouse, 'warehouse_code') else warehouse.name,
                "warehouse_name": warehouse.warehouse_name,
                "total_pincodes": pincode_count,
                "is_active": not warehouse.disabled if hasattr(warehouse, 'disabled') else True,
                "city": warehouse.city if hasattr(warehouse, 'city') else "",
                "state": warehouse.state if hasattr(warehouse, 'state') else ""
            }
            
        except Exception as e:
            logger.error(f"Error getting warehouse stats: {e}")
            return {}
