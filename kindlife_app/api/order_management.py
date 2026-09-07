# order_management.py
# API endpoint for CS Cart to handle order cancellations, returns, and replacements

import frappe
from frappe import _
import json

@frappe.whitelist(allow_guest=False)
def handle_order_event(data):
    """
    Main API endpoint to handle order events from CS Cart.
    
    Expected JSON structure:
    {
        "event_type": "cancellation" | "return" | "replacement",
        "sales_order_id": "SO-24-25-000209",
        "reason": "Customer requested cancellation.",
        "items": [
            {
                "item_code": "ITM-001",
                "qty": 1
            }
        ]
    }
    """
    try:
        if isinstance(data, str):
            data = json.loads(data)
            
        validate_event_data(data)
        
        event_type = data.get("event_type").lower()
        sales_order_id = data.get("sales_order_id")
        items_to_process = data.get("items", [])
        
        so = frappe.get_doc("Sales Order", sales_order_id)
        
        if event_type == 'cancellation':
            response = handle_cancellation(so, items_to_process)
        elif event_type in ['return', 'replacement']:
            response = handle_return(so, items_to_process)
        else:
            frappe.throw(_("Invalid event_type specified."))
            
        frappe.db.commit()
        return response

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Order Event Failed - {data.get('sales_order_id', 'Unknown')}"
        )
        return {
            "status": "error",
            "message": str(e),
            "sales_order_id": data.get("sales_order_id")
        }

def validate_event_data(data):
    """Validate incoming event data"""
    required_fields = ["event_type", "sales_order_id", "items"]
    for field in required_fields:
        if not data.get(field):
            frappe.throw(_(f"Missing required field: {field}"))

    if not data.get("items"):
        frappe.throw(_("At least one item is required."))

    for item in data.get("items"):
        if not item.get("item_code") or not item.get("qty"):
            frappe.throw(_("Each item must have item_code and qty."))

def handle_cancellation(so, items_to_cancel):
    """Handle cancellation of items before delivery using db_set."""
    if so.docstatus != 1:
        frappe.throw(_("Sales Order must be submitted to be cancelled."))

    for item_data in items_to_cancel:
        item_code = item_data.get("item_code")
        qty_to_cancel = frappe.utils.flt(item_data.get("qty"))

        so_item = frappe.db.get_value(
            "Sales Order Item",
            {"parent": so.name, "item_code": item_code},
            ["name", "qty", "delivered_qty"],
            as_dict=True
        )

        if not so_item:
            frappe.throw(_(f"Item {item_code} not found in Sales Order {so.name}."))

        if so_item.delivered_qty > 0:
            frappe.throw(_(f"Item {item_code} has already been delivered and cannot be cancelled. Please process a return instead."))

        new_qty = so_item.qty - qty_to_cancel
        update_dict = {"qty": max(0, new_qty)}

        frappe.db.set_value("Sales Order Item", so_item.name, update_dict)

    # After updating items, reload the doc to run calculations
    so.reload()
    
    # Manually trigger recalculation of totals
    so.calculate_taxes_and_totals()

    # Use db_set to update totals on the submitted document
    so.db_set({
        "total": so.total,
        "net_total": so.net_total,
        "grand_total": so.grand_total,
        "base_total": so.base_total,
        "base_net_total": so.base_net_total,
        "base_grand_total": so.base_grand_total,
        "total_qty": so.total_qty,
        "total_taxes_and_charges": so.total_taxes_and_charges,
    })
    
    # Recalculate and update the document status
    so.set_status(update=True)

    frappe.msgprint(_("Sales Order items have been updated."))
    return {"status": "success", "message": "Items updated successfully."}


def handle_return(so, items_to_return):
    """Handle return of items after delivery."""
    if so.docstatus != 1:
        frappe.throw(_("Sales Order must be submitted to process returns."))

    # Check for submitted Delivery Note
    dn_name = frappe.db.get_value("Delivery Note Item", {"against_sales_order": so.name}, "parent")
    if not dn_name or not frappe.db.get_value("Delivery Note", dn_name, "docstatus") == 1:
        frappe.throw(_("No submitted Delivery Note found for this Sales Order. Cannot process return."))

    # Create Sales Return
    return_dn = frappe.new_doc("Delivery Note")
    return_dn.is_return = 1
    return_dn.set("return_against", dn_name)
    
    # Add items to return
    for item_data in items_to_return:
        dn_item = frappe.get_doc("Delivery Note Item", {"parent": dn_name, "item_code": item_data.get("item_code")})
        return_dn.append("items", {
            "item_code": dn_item.item_code,
            "qty": item_data.get("qty"),
            "warehouse": dn_item.warehouse,
            "against_delivery_note_item": dn_item.name,
            "rate": dn_item.rate,
        })

    return_dn.insert(ignore_permissions=True)
    return_dn.submit()
    
    frappe.msgprint(_(f"Sales Return {return_dn.name} created and submitted."))
    return {"status": "success", "message": f"Sales Return {return_dn.name} created."}

def get_so_item(so_doc, item_code):
    """Helper to find an item in a Sales Order."""
    for item in so_doc.items:
        if item.item_code == item_code:
            return item
    frappe.throw(_(f"Item {item_code} not found in Sales Order {so_doc.name}."))
