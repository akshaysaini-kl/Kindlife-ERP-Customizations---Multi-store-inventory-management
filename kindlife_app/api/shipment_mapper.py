# shipment_mapper.py
# API endpoint for CS Cart to map shipment_id to Sales Order Item, Pick List, and Purchase Order Item

import frappe
from frappe import _
import json
from kindlife_app.utils.shipment_utils import sync_shipment_docs_for_so

@frappe.whitelist(allow_guest=False)
def map_shipment_id(data):
    """
    API endpoint to map shipment_id to Sales Order Item, Pick List, and Purchase Order Item
    
    Expected JSON structure:
    {
        "sales_order_id": "SO-24-25-000209",
        "items": [
            {
                "item_code": "ITM-001",
                "shipment_id": "SH-12345",
                "awb_number": "12345"
            },
            {
                "item_code": "ITM-002",
                "shipment_id": "SH-12346",
                "awb_number": "12345"
            }
        ]
    }
    """
    
    try:
        # Parse data if it's a string
        if isinstance(data, str):
            data = json.loads(data)
        
        # Validate required fields
        validate_shipment_data(data)
        
        sales_order_id = data.get("sales_order_id")
        items = data.get("items", [])
        
        # Map shipment ID for each item
        mapped_items = []
        for item in items:
            map_shipment_id_for_item(sales_order_id, item)
            mapped_items.append({
                "item_code": item.get("item_code"),
                "shipment_id": item.get("shipment_id"),
                "status": "success"
            })

        
        # Propagate shipment fields to linked PL/DN/PO child rows
        sync_shipment_docs_for_so(sales_order_id)

        frappe.db.commit()
        
        return {
            "status": "success",
            "message": "Shipment IDs mapped successfully",
            "sales_order_id": sales_order_id,
            "mapped_items": mapped_items
        }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Shipment ID Mapping Failed - {data.get('sales_order_id', 'Unknown')}"
        )
        return {
            "status": "error",
            "message": str(e),
            "sales_order_id": data.get("sales_order_id")
        }

def validate_shipment_data(data):
    """Validate incoming shipment data"""
    required_fields = ["sales_order_id", "items"]

    for field in required_fields:
        if not data.get(field):
            frappe.throw(_(f"Missing required field: {field}"))

    if not data.get("items") or len(data.get("items")) == 0:
        frappe.throw(_("At least one item is required"))

    for item in data.get("items"):
        if not item.get("item_code") or not item.get("shipment_id"):
            frappe.throw(_("Each item must have item_code and shipment_id"))

def map_shipment_id_for_item(sales_order_id, item_data):
    """Map shipment_id for a single item"""
    item_code = item_data.get("item_code")
    shipment_id = item_data.get("shipment_id")
    awb_number = item_data.get("awb_number")
    
    # Get the Sales Order Item
    so_item = frappe.db.get_value(
        "Sales Order Item",
        {"parent": sales_order_id, "item_code": item_code},
        ["name", "custom_fulfilled_by", "purchase_order"],
        as_dict=True
    )
    
    if not so_item:
        frappe.throw(_(f"Item {item_code} not found in Sales Order {sales_order_id}"))
    
    # Update Sales Order Item
    frappe.db.set_value("Sales Order Item", so_item.name, {
        "custom_shipment_id": shipment_id,
        "custom_awb_number": awb_number
    })
    
    # Determine fulfillment type and update related documents
    if (so_item.custom_fulfilled_by or "").lower() == "brand":
        update_purchase_order_item_shipment(so_item, shipment_id, awb_number)
    else: # Warehouse
        update_pick_list_shipment(so_item, sales_order_id, shipment_id)

def update_purchase_order_item_shipment(so_item, shipment_id, awb_number=None):
    """Update shipment_id on the related Purchase Order Item"""
    if not so_item.purchase_order:
        frappe.log_error(f"Brand fulfilled item {so_item.name} has no PO linked.")
        return

    po_item = frappe.db.get_value(
        "Purchase Order Item",
        {"sales_order_item": so_item.name},
        "name"
    )
    
    if po_item:
        frappe.db.set_value("Purchase Order Item", po_item, {
            "custom_shipment_id": shipment_id,
            "custom_awb_number": awb_number
        })

def update_pick_list_shipment(so_item, sales_order_id, shipment_id):
    """Update shipment_id on the related Pick List Item row"""
    # Find the specific Pick List Item row that links to this Sales Order Item
    pl_item_name = frappe.db.get_value(
        "Pick List Item",
        {"sales_order_item": so_item.name},
        "name"
    )

    if pl_item_name:
        frappe.db.set_value("Pick List Item", pl_item_name, "custom_shipment_id", str(shipment_id), update_modified=False)
    else:
        frappe.log_error(
            f"Could not find Pick List Item for Sales Order Item {so_item.name}",
            "Shipment ID Mapping: Pick List Item Not Found"
        )
