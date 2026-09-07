import frappe
from frappe import _
import json
from typing import List, Dict, Optional
from kindlife_app.services.warehouse_service import WarehouseService
from kindlife_app.services.geocoding_service import GeocodingService

@frappe.whitelist()
def find_nearest_warehouse_with_inventory(items, shipping_address_line1, shipping_address_line2=None, shipping_city=None, shipping_state=None, shipping_pincode=None, shipping_rule=None):
    """
    Find the nearest warehouse that has inventory for the given items
    
    This method:
    1. Geocodes the customer's shipping address to get exact coordinates
    2. Finds all warehouses that service the pincode
    3. Sorts them by distance to the customer
    4. Checks inventory in each warehouse for the requested items
    5. Returns the nearest warehouse that can fulfill the order
    
    API Endpoint: /api/method/kindlife_app.api.logistics.find_nearest_warehouse_with_inventory
    
    Args:
        address_line1: Customer's shipping address line 1
        city: Customer's city
        state: Customer's state
        pincode: Customer's pincode
        items: JSON string of items to check inventory for, format: [{"item_code": "ITEM001", "qty": 2}, ...]
    """
    # geocoding_service = GeocodingService()
    warehouse_service = WarehouseService()
    
  
    # Parse items if provided as string
    if items and isinstance(items, str):
        try:
            items = json.loads(items)
        except:
            frappe.throw("Invalid items format. Expected JSON array.")
    
    # Step 1: Geocode the customer's address to get exact coordinates
    warehouses_info = warehouse_service.find_the_shipping_warehouses(
        items, shipping_address_line1, None, shipping_city, shipping_state, shipping_pincode, None
    )
    return warehouses_info
    
  
    # if not customer_coords:
    #     frappe.msgprint("Could not geocode customer address. Falling back to pincode-based assignment.")
    #     # Fallback to pincode-based assignment
    #     return warehouse_service.find_warehouse_for_pincode(pincode)
    
    # customer_lat, customer_lon, customer_pincode = customer_coords
    
    # Step 2: Get all warehouses that service this pincode
    # serviceable_warehouses = frappe.get_all(
    #     "Warehouse Servicable Pincode",
    #     filters={"pincode": customer_pincode},
    #     fields=["warehouse", "tat", "priority"]
    # )
    
    # if not serviceable_warehouses:
    #     frappe.msgprint(f"No warehouses service pincode {pincode}")
    #     return None
    
    # Step 3: Calculate distance to each warehouse and sort by distance
    # warehouse_distances = []
    # for sp in serviceable_warehouses:
    #     warehouse = frappe.get_doc("Warehouse", sp.warehouse)
        
    #     # Skip warehouses without coordinates
    #     if not warehouse.latitude or not warehouse.longitude:
    #         continue
        
    #     # Calculate distance
    #     distance = warehouse_service._calculate_distance(
    #         customer_lat,
    #         customer_lon,
    #         float(warehouse.latitude),
    #         float(warehouse.longitude)
    #     )
        
    #     warehouse_distances.append({
    #         "warehouse": warehouse,
    #         "service_pincode": sp,
    #         "distance": distance
    #     })
    
    # Sort by distance (nearest first)
    # warehouse_distances.sort(key=lambda x: x["distance"])
    
    # Step 4: If items provided, check inventory in each warehouse
    # if items:
    #     for wd in warehouse_distances:
    #         warehouse = wd["warehouse"]
            
    #         # Check if all items are available in this warehouse
    #         all_items_available = True
            
    #         for item in items:
    #             item_code = item.get("item_code")
    #             required_qty = item.get("qty", 1)
                
    #             # Check bin for available quantity
    #             bin_data = frappe.db.get_value(
    #                 "Bin",
    #                 {"item_code": item_code, "warehouse": warehouse.name},
    #                 ["actual_qty", "reserved_qty"],
    #                 as_dict=True
    #             )
                
    #             if not bin_data or (bin_data.actual_qty - bin_data.reserved_qty) < required_qty:
    #                 all_items_available = False
    #                 break
            
    #         # If all items available in this warehouse, return it
    #         if all_items_available:
    #             return {
    #                 "warehouse_id": warehouse.name,
    #                 "warehouse_code": warehouse.warehouse_code if hasattr(warehouse, 'warehouse_code') else warehouse.name,
    #                 "warehouse_name": warehouse.warehouse_name,
    #                 "tat": wd["service_pincode"].tat,
    #                 "distance_km": round(wd["distance"], 2),
    #                 "customer_coordinates": {
    #                     "latitude": customer_lat,
    #                     "longitude": customer_lon
    #                 },
    #                 "inventory_checked": True,
    #                 "can_fulfill": True
    #             }
    
    # If no items provided or no warehouse can fulfill all items, return the nearest warehouse
    # if warehouse_distances:
    #     nearest = warehouse_distances[0]
    #     warehouse = nearest["warehouse"]
        
    #     return {
    #         "warehouse_id": warehouse.name,
    #         "warehouse_code": warehouse.warehouse_code if hasattr(warehouse, 'warehouse_code') else warehouse.name,
    #         "warehouse_name": warehouse.warehouse_name,
    #         "tat": nearest["service_pincode"].tat,
    #         "distance_km": round(nearest["distance"], 2),
    #         "customer_coordinates": {
    #             "latitude": customer_lat,
    #             "longitude": customer_lon
    #         },
    #         "inventory_checked": bool(items),
    #         "can_fulfill": False if items else None
    #     }
    
    # # Fallback to default warehouse if no warehouses with coordinates found
    # return warehouse_service._get_default_warehouse()

@frappe.whitelist()
def geocode_customer_address(shipping_address_line1, shipping_city=None, shipping_state=None, shipping_pincode=None):
    """
    Geocode a customer's address to get exact latitude and longitude
    
    This is the main endpoint for getting customer coordinates from their shipping address.
    
    API Endpoint: /api/method/kindlife_app.api.logistics.geocode_customer_address
    
    Args:
        address_line1: Customer's shipping address line 1
        city: Customer's city
        state: Customer's state
        pincode: Customer's pincode
        
    Returns:
        Dictionary with latitude, longitude, and formatted address
    """
    geocoding_service = GeocodingService()
    
    # Geocode the address
    coords = geocoding_service.geocode_address_with_cache(
        shipping_address_line1, None, shipping_city, shipping_state, shipping_pincode
    )
    
    if not coords:
        return {
            "success": False,
            "message": "Could not geocode address",
            "latitude": None,
            "longitude": None
        }
    
    # Get formatted address
    formatted_address = f"{shipping_address_line1}"
    if shipping_city:
        formatted_address += f", {shipping_city}"
    if shipping_state:
        formatted_address += f", {shipping_state}"
    if shipping_pincode:
        formatted_address += f" {shipping_pincode}"
    
    return {
        "success": True,
        "latitude": coords[0],
        "longitude": coords[1],
        "formatted_address": formatted_address
    }

@frappe.whitelist()
def get_warehouses_for_pincode(pincode):
    """
    Get all warehouses that service a specific pincode
    
    API Endpoint: /api/method/kindlife_app.api.logistics.get_warehouses_for_pincode
    """
    service = WarehouseService()
    warehouses = service.get_warehouses_for_pincode(pincode)
    return {"warehouses": warehouses}

@frappe.whitelist()
def get_warehouse_coverage(warehouse_id):
    """
    Get all pincodes covered by a warehouse
    
    API Endpoint: /api/method/kindlife_app.api.logistics.get_warehouse_coverage
    """
    service = WarehouseService()
    pincodes = service.get_warehouse_coverage(warehouse_id)
    return {"pincodes": pincodes}

@frappe.whitelist()
def update_warehouse_coverage(warehouse_id, pincodes, tat=None, priority=None):
    """
    Update the pincodes covered by a warehouse
    
    API Endpoint: /api/method/kindlife_app.api.logistics.update_warehouse_coverage
    """
    service = WarehouseService()
    
    # Convert pincodes from string to list if needed
    if isinstance(pincodes, str):
        pincodes = json.loads(pincodes)
    
    # Set default values
    if not tat:
        tat = "1-2 days"
    if not priority:
        priority = 1
    else:
        priority = int(priority)
    
    success = service.update_warehouse_coverage(
        warehouse_id,
        pincodes,
        tat,
        priority
    )
    
    if success:
        return {"message": "Warehouse coverage updated successfully"}
    else:
        return {"message": "Failed to update warehouse coverage"}

@frappe.whitelist()
def get_warehouse_stats(warehouse_id):
    """
    Get statistics for a warehouse
    
    API Endpoint: /api/method/kindlife_app.api.logistics.get_warehouse_stats
    """
    service = WarehouseService()
    stats = service.get_warehouse_stats(warehouse_id)
    return stats

@frappe.whitelist()
def check_warehouse_service_settings():
    """
    Check if the Warehouse Service Settings doctype exists
    
    API Endpoint: /api/method/kindlife_app.api.logistics.check_warehouse_service_settings
    """
    doctype_exists = frappe.db.exists('DocType', 'Warehouse Service Settings')
    return {
        "exists": bool(doctype_exists),
        "value": doctype_exists
    }

@frappe.whitelist()
def get_geocoding_cache_stats():
    """
    Get statistics about the geocoding cache
    
    API Endpoint: /api/method/kindlife_app.api.logistics.get_geocoding_cache_stats
    """
    # Check if Geocoded Address doctype exists
    if not frappe.db.exists("DocType", "Geocoded Address"):
        return {
            "total_entries": 0,
            "total_hits": 0,
            "cache_hits": 0,
            "cache_hit_rate": 0,
            "estimated_savings_usd": 0
        }
    
    # Calculate total entries
    total_entries = frappe.db.count("Geocoded Address")
    
    # Calculate total hits and savings
    result = frappe.db.sql("""
        SELECT 
            COUNT(*) as total_entries,
            SUM(hit_count) as total_hits,
            SUM(hit_count - 1) as cache_hits
        FROM `tabGeocoded Address`
    """, as_dict=True)
    
    if not result or not result[0].total_entries:
        return {
            "total_entries": 0,
            "total_hits": 0,
            "cache_hits": 0,
            "cache_hit_rate": 0,
            "estimated_savings_usd": 0
        }
    
    stats = result[0]
    
    # Calculate hit rate and savings
    cache_hit_rate = 0
    if stats.total_hits > 0:
        cache_hit_rate = (stats.cache_hits or 0) / stats.total_hits
    
    # Google Maps Geocoding API costs $5 per 1000 requests
    estimated_savings_usd = (stats.cache_hits or 0) * 0.005
    
    return {
        "total_entries": stats.total_entries,
        "total_hits": stats.total_hits,
        "cache_hits": stats.cache_hits,
        "cache_hit_rate": round(cache_hit_rate * 100, 2),
        "estimated_savings_usd": round(estimated_savings_usd, 2)
    }
