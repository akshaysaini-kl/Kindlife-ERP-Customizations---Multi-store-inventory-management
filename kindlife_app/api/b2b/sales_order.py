import frappe
from frappe import _
from frappe.utils import nowdate, flt, add_days
import json


@frappe.whitelist(methods=['POST'])
def create_b2b_sales_order(data):
    """
    Create B2B Sales Order using customer and item information.
    
    Expected JSON structure:
    {
        "customer": "CUST-00123",
        "price_list": "Standard Selling",
        "shipping_address_name": "ADDR-00001",
        "billing_address_name": "ADDR-00002",
        "po_no": "PO-2024-001",
        "po_date": "2024-12-02",
        "delivery_date": "2024-12-10",
        "items": [
            {
                "item_code": "ITM-001",
                "qty": 10,
                "rate": 100.00
            }
        ]
    }
    
    Args:
        data (dict or str): Sales order data
    
    Returns:
        dict: Response with sales order details or error
    """
    try:
        # Parse data if it's a string
        if isinstance(data, str):
            data = json.loads(data)
        
        # Validate required fields
        validate_sales_order_data(data)
        
        # Get customer name (in case full customer object is passed)
        customer = data.get("customer")
        if isinstance(customer, dict):
            customer = customer.get("name")
        
        # Prepare Sales Order document
        sales_order = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": customer,
            "order_type": "Sales",
            "transaction_date": data.get("transaction_date", nowdate()),
            "delivery_date": data.get("delivery_date", add_days(nowdate(), 7)),
            
            # Purchase Order reference
            "po_no": data.get("po_no"),
            "po_date": data.get("po_date", nowdate()),
            
            # Addresses
            "shipping_address_name": data.get("shipping_address_name"),
            "customer_address": data.get("billing_address_name") or data.get("customer_address") or data.get("shipping_address_name"),
            
            # Pricing
            "selling_price_list": data.get("price_list"),
            "currency": data.get("currency", "INR"),
            
            # Items
            "items": prepare_sales_order_items(data.get("items", [])),
            
            # Company
            "company": data.get("company") or frappe.defaults.get_user_default("Company"),
            
            # Custom fields
            "custom_type": "B2B"
        })
        
        # Add additional fields if provided
        if data.get("contact_person"):
            sales_order.contact_person = data.get("contact_person")
        
        if data.get("taxes_and_charges"):
            sales_order.taxes_and_charges = data.get("taxes_and_charges")
        
        # Insert the Sales Order
        sales_order.insert(ignore_permissions=True)
        
        # Submit if requested
        if data.get("submit"):
            sales_order.submit()
        
        # Commit the transaction
        frappe.db.commit()
        
        return {
            "status": "success",
            "message": "Sales Order created successfully",
            "sales_order_id": sales_order.name,
            "sales_order_name": sales_order.name,
            "customer": sales_order.customer,
            "grand_total": sales_order.grand_total,
            "status": sales_order.status,
            "docstatus": sales_order.docstatus
        }
    
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"B2B Sales Order Creation Failed - {data.get('po_no', 'Unknown')}"
        )
        frappe.response.http_status_code = 500
        return {
            "status": "error",
            "message": str(e),
            "po_no": data.get("po_no")
        }


def validate_sales_order_data(data):
    """Validate incoming sales order data"""
    required_fields = ["customer", "items"]
    
    for field in required_fields:
        if not data.get(field):
            frappe.throw(_(f"Missing required field: {field}"))
    
    # Validate items
    if not data.get("items") or len(data.get("items")) == 0:
        frappe.throw(_("At least one item is required"))
    
    for item in data.get("items"):
        if not item.get("item_code"):
            frappe.throw(_("Each item must have item_code"))
        if not item.get("qty"):
            frappe.throw(_("Each item must have qty"))


def prepare_sales_order_items(items_data):
    """Prepare items for Sales Order"""
    items = []
    
    for item in items_data:
        # Validate item exists
        if not frappe.db.exists("Item", item.get("item_code")):
            frappe.throw(_(f"Item {item.get('item_code')} does not exist in system"))
        
        item_dict = {
            "item_code": item.get("item_code"),
            "qty": flt(item.get("qty")),
            "delivery_date": item.get("delivery_date", add_days(nowdate(), 7))
        }
        
        # Add rate if provided
        if item.get("rate"):
            item_dict["rate"] = flt(item.get("rate"))
        
        # Add warehouse if provided
        if item.get("warehouse"):
            item_dict["warehouse"] = item.get("warehouse")
        
        # Add description if provided
        if item.get("description"):
            item_dict["description"] = item.get("description")
        
        # Add discount if provided
        if item.get("discount_percentage"):
            item_dict["discount_percentage"] = flt(item.get("discount_percentage"))
        
        items.append(item_dict)
    
    return items


@frappe.whitelist(methods=['POST'])
def create_b2b_sales_order_from_buyer_skus(gstin, city, buyers_skus, items_with_qty, po_no=None, po_date=None, delivery_date=None):
    """
    Create B2B Sales Order by first fetching customer via address and items via buyer SKUs.
    This is a convenience API that combines get_customer_via_address and get_items_from_customer.
    
    Args:
        gstin (str): GST Identification Number
        city (str): City name
        buyers_skus (list or str): List of buyer SKU codes
        items_with_qty (dict or str): Dictionary mapping buyer_sku to qty, e.g., {"SKU-001": 10, "SKU-002": 5}
        po_no (str, optional): Purchase Order number
        po_date (str, optional): Purchase Order date
        delivery_date (str, optional): Delivery date
    
    Returns:
        dict: Response with sales order details or error
    """
    try:
        # Parse JSON strings if needed
        if isinstance(buyers_skus, str):
            buyers_skus = json.loads(buyers_skus)
        
        if isinstance(items_with_qty, str):
            items_with_qty = json.loads(items_with_qty)
        
        # Step 1: Get customer via address
        from kindlife_app.api.b2b.address import get_customer_via_address
        
        customer_response = get_customer_via_address(gstin=gstin, city=city)
        
        if customer_response.get("status") != "success":
            return customer_response
        
        customer = customer_response.get("customer")
        address_details = customer_response.get("address_details")
        
        if not customer:
            frappe.response.http_status_code = 404
            return {
                "status": "error",
                "message": "No customer found for the given address"
            }
        
        # Extract customer details
        customer_name = customer.get("name") if isinstance(customer, dict) else customer
        price_list = customer.get("default_price_list") if isinstance(customer, dict) else None
        
        if not price_list:
            frappe.response.http_status_code = 400
            return {
                "status": "error",
                "message": "Customer does not have a default price list configured"
            }
        
        # Get shipping and billing addresses from address_details
        shipping_address_name = None
        billing_address_name = None
        
        if address_details:
            # Find shipping address (address_type = 'Shipping')
            for addr in address_details:
                if addr.get("address_type") == "Shipping":
                    shipping_address_name = addr.get("name")
                    break
            
            # Find billing address (address_type = 'Billing')
            for addr in address_details:
                if addr.get("address_type") == "Billing":
                    billing_address_name = addr.get("name")
                    break
            
            # Fallback: if no specific type found, use first address
            if not shipping_address_name:
                shipping_address_name = address_details[0].get("name")
            if not billing_address_name:
                billing_address_name = address_details[0].get("name")
        
        # Step 2: Get items from buyer SKUs
        from kindlife_app.api.b2b.item import get_items_from_customer
        
        items_response = get_items_from_customer(
            buyers_skus=buyers_skus,
            customer=customer_name,
            price_list=price_list
        )
        
        if items_response.get("status") != "success":
            return items_response
        
        matched_items = items_response.get("items", [])
        
        if not matched_items:
            frappe.response.http_status_code = 404
            return {
                "status": "error",
                "message": "No items found for the given buyer SKUs"
            }
        
        # Step 3: Prepare items for sales order with quantities
        sales_order_items = []
        for item in matched_items:
            buyer_sku = item.get("buyer_sku")
            qty = items_with_qty.get(buyer_sku)
            
            if qty:
                sales_order_items.append({
                    "item_code": item.get("item_code"),
                    "qty": qty,
                    "rate": item.get("price_list_rate")
                })
        
        if not sales_order_items:
            frappe.response.http_status_code = 400
            return {
                "status": "error",
                "message": "No valid items with quantities found"
            }
        
        # Step 4: Create Sales Order
        sales_order_data = {
            "customer": customer_name,
            "price_list": price_list,
            "shipping_address_name": shipping_address_name,
            "billing_address_name": billing_address_name,
            "po_no": po_no,
            "po_date": po_date or nowdate(),
            "delivery_date": delivery_date or add_days(nowdate(), 7),
            "items": sales_order_items
        }
        
        return create_b2b_sales_order(sales_order_data)
    
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="B2B Sales Order from Buyer SKUs Failed"
        )
        frappe.response.http_status_code = 500
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(methods=['GET'])
def get_sales_order_by_po(po_no):
    """
    Get Sales Order details by PO Number
    """
    if not po_no:
        return {
            "message": "No SO found"
        }

    sales_orders = frappe.get_list("Sales Order", filters={"po_no": po_no}, fields=["name", "customer", "grand_total", "status", "transaction_date", "delivery_date", "price_list","po_date","shipping_address_name"])
    
    if not sales_orders:
        return {
            "message": "No SO found"
        }
    
    # helper for fetching items
    sales_order = sales_orders[0]
    # return frappe.get_doc("Sales Order", sales_order.name)
    items = frappe.get_all("Sales Order Item", filters={"parent": sales_order.name}, fields=["item_code", "item_name", "qty", "rate", "amount"])
    sales_order["items"] = items

    return sales_order
