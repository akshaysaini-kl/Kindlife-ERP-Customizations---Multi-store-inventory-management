import frappe
import json


@frappe.whitelist()
def get_items_from_customer(buyers_skus, customer, price_list):
    """
    Get items based on buyer SKUs, customer, and price list.
    
    Args:
        buyers_skus (list or str): List of buyer SKU codes (ref_code in Item Customer Detail)
        customer (str): Customer ID/name
        price_list (str): Price list name
    
    Returns:
        dict: Response containing matched items with their details and prices
        
    Logic:
        1. Parse buyers_skus if it's a JSON string
        2. Search for items where ref_code in Item Customer Detail matches buyer SKUs
        3. Fetch item prices from the specified price_list
        4. Return matched items with complete details
    """
    try:
        # Parse buyers_skus if it's a JSON string
        if isinstance(buyers_skus, str):
            try:
                buyers_skus = json.loads(buyers_skus)
            except json.JSONDecodeError:
                frappe.response.http_status_code = 400
                return {
                    "status": "error",
                    "message": "buyers_skus must be a valid JSON array"
                }
        
        # Validate required parameters
        if not buyers_skus or not isinstance(buyers_skus, list):
            frappe.response.http_status_code = 400
            return {
                "status": "error",
                "message": "buyers_skus is required and must be an array"
            }
        
        if not customer:
            frappe.response.http_status_code = 400
            return {
                "status": "error",
                "message": "customer is required"
            }
        
        if not price_list:
            frappe.response.http_status_code = 400
            return {
                "status": "error",
                "message": "price_list is required"
            }
        
        # Search for items matching the buyer SKUs in Item Customer Detail
        matched_items = []
        not_found_skus = []
        
        for buyer_sku in buyers_skus:
            # Find item customer detail with matching ref_code
            item_customer_details = frappe.get_all(
                "Item Customer Detail",
                filters={
                    "ref_code": buyer_sku,
                    "customer_name": customer
                },
                fields=["parent", "ref_code", "customer_name"],
                limit=1
            )
            
            if not item_customer_details:
                not_found_skus.append(buyer_sku)
                continue
            
            item_code = item_customer_details[0].parent
            
            # Get item details
            item = frappe.get_cached_doc("Item", item_code)
            
            # Get item price from the specified price list
            item_price = frappe.db.get_value(
                "Item Price",
                {
                    "item_code": item_code,
                    "price_list": price_list
                },
                ["price_list_rate", "currency"],
                as_dict=True
            )
            
            # Prepare item data
            item_data = {
                "item_code": item.name,
                "item_name": item.item_name,
                "buyer_sku": buyer_sku,
                "description": item.description,
                "stock_uom": item.stock_uom,
                "item_group": item.item_group,
                "price_list_rate": item_price.price_list_rate if item_price else None,
                "currency": item_price.currency if item_price else None,
                "has_variants": item.has_variants if hasattr(item, 'has_variants') else 0,
                "is_stock_item": item.is_stock_item if hasattr(item, 'is_stock_item') else 1
            }
            
            # Add custom fields if they exist
            if hasattr(item, 'custom_mrp'):
                item_data['mrp'] = item.custom_mrp
            if hasattr(item, 'custom_ean'):
                item_data['ean'] = item.custom_ean
            if hasattr(item, 'gst_hsn_code'):
                item_data['hsn_code'] = item.gst_hsn_code
            
            matched_items.append(item_data)
        
        # Prepare response
        response = {
            "status": "success",
            "items": matched_items,
            "total_matched": len(matched_items),
            "total_requested": len(buyers_skus)
        }
        
        # Add not found SKUs if any
        if not_found_skus:
            response["not_found_skus"] = not_found_skus
            response["total_not_found"] = len(not_found_skus)
        
        return response
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Items from Customer API Error")
        frappe.response.http_status_code = 500
        return {
            "status": "error",
            "message": str(e)
        }
