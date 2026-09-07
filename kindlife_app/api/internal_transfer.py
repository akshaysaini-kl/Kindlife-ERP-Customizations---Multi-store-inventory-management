"""
Internal Transfer - Batch and Serial Tracking
Handles transfer of batch/serial data from Pick List to Purchase Receipt
for internal company transfers.

Author: Development Team
Created: 2026-05-19
Version: 1.0.0
"""

import frappe
from frappe import _
from typing import Dict, List, Optional


@frappe.whitelist()
def get_pick_list_batch_serial_data(sales_order: str) -> Dict:
    """
    Get batch and serial data from Pick List for a Sales Order.
    Used to auto-populate Purchase Receipt in internal transfers.
    
    Args:
        sales_order: Sales Order name
    
    Returns:
        {
            "success": bool,
            "pick_list": str (Pick List name),
            "data": {
                "ITEM-001": {
                    "BATCH-A": {
                        "expected_qty": 10,
                        "serials": ["SN001", "SN002", ...],
                        "warehouse": "WH-A"
                    }
                }
            }
        }
    """
    try:
        # Find submitted Pick List for this Sales Order
        pick_lists = frappe.get_all(
            "Pick List",
            filters={
                "sales_order": sales_order,
                "docstatus": 1  # Submitted only
            },
            fields=["name", "creation"],
            order_by="`tabPick List`.creation desc",
            limit=1
        )
        
        if not pick_lists:
            return {
                "success": False,
                "message": _("No submitted Pick List found for Sales Order {0}").format(sales_order)
            }
        
        pick_list_name = pick_lists[0].name
        pick_list = frappe.get_doc("Pick List", pick_list_name)
        
        # Extract batch-serial mapping
        batch_serial_map = {}
        
        for location in pick_list.locations:
            item_code = location.item_code
            batch_no = location.batch_no
            
            if not batch_no:
                continue  # Skip items without batch
            
            # Initialize item if not exists
            if item_code not in batch_serial_map:
                batch_serial_map[item_code] = {}
            
            # Parse serials (line-separated)
            serials = []
            if location.serial_no:
                serials = [s.strip() for s in location.serial_no.split("\n") if s.strip()]
            
            # Store batch data
            if batch_no not in batch_serial_map[item_code]:
                batch_serial_map[item_code][batch_no] = {
                    "expected_qty": 0,
                    "serials": [],
                    "warehouse": location.warehouse
                }
            
            # Accumulate data (in case same batch appears multiple times)
            batch_serial_map[item_code][batch_no]["expected_qty"] += location.picked_qty or 0
            batch_serial_map[item_code][batch_no]["serials"].extend(serials)
        
        return {
            "success": True,
            "pick_list": pick_list_name,
            "data": batch_serial_map,
            "message": _("Found Pick List {0} with {1} items").format(
                pick_list_name, 
                len(batch_serial_map)
            )
        }
        
    except Exception as e:
        frappe.log_error(
            title="Get Pick List Data Error",
            message=f"Sales Order: {sales_order}\nError: {str(e)}"
        )
        return {
            "success": False,
            "message": _("Error fetching Pick List data: {0}").format(str(e))
        }


@frappe.whitelist()
def get_internal_po_sales_order(purchase_order: str) -> Optional[str]:
    """
    Get the linked Sales Order for an Internal Purchase Order.
    
    Args:
        purchase_order: Purchase Order name
    
    Returns:
        Sales Order name or None
    """
    try:
        po = frappe.get_doc("Purchase Order", purchase_order)
        
        # Check if it's an internal PO
        if not po.is_internal_supplier:
            return None
        
        # Get inter-company reference (Sales Order)
        return po.inter_company_order_reference
        
    except Exception as e:
        frappe.log_error(
            title="Get Internal PO Sales Order Error",
            message=f"Purchase Order: {purchase_order}\nError: {str(e)}"
        )
        return None


@frappe.whitelist()
def check_pick_list_exists(sales_order: str) -> Dict:
    """
    Check if a submitted Pick List exists for a Sales Order.
    Also checks if an active Internal Purchase Order already exists.
    Used to validate Internal Purchase Order creation.
    
    Args:
        sales_order: Sales Order name
    
    Returns:
        {
            "exists": bool,
            "pick_list": str (if exists),
            "message": str,
            "can_create_po": bool,
            "existing_po": str (if exists)
        }
    """
    try:
        # Check if Pick List exists
        pick_lists = frappe.get_all(
            "Pick List",
            filters={
                "sales_order": sales_order,
                "docstatus": 1  # Submitted only
            },
            fields=["name"],
            order_by="`tabPick List`.creation desc",
            limit=1
        )
        
        pick_list_exists = bool(pick_lists)
        pick_list_name = pick_lists[0].name if pick_lists else None
        
        # Check if an active Internal Purchase Order already exists
        existing_pos = frappe.get_all(
            "Purchase Order",
            filters={
                "inter_company_order_reference": sales_order,
                "is_internal_supplier": 1,
                "docstatus": ["!=", 2]  # Not cancelled (0=Draft, 1=Submitted)
            },
            fields=["name", "docstatus"],
            order_by="`tabPurchase Order`.creation desc",
            limit=1
        )
        
        if existing_pos:
            po = existing_pos[0]
            po_status = "Draft" if po.docstatus == 0 else "Submitted"
            return {
                "exists": pick_list_exists,
                "pick_list": pick_list_name,
                "can_create_po": False,
                "existing_po": po.name,
                "po_status": po_status,
                "message": _(
                    "Internal Purchase Order {0} ({1}) already exists for this Sales Order. "
                    "Please cancel or amend it before creating a new one."
                ).format(po.name, po_status)
            }
        
        if pick_list_exists:
            return {
                "exists": True,
                "pick_list": pick_list_name,
                "can_create_po": True,
                "message": _("Submitted Pick List {0} found").format(pick_list_name)
            }
        else:
            return {
                "exists": False,
                "can_create_po": False,
                "message": _("No submitted Pick List found for Sales Order {0}").format(sales_order)
            }
            
    except Exception as e:
        frappe.log_error(
            title="Check Pick List Error",
            message=f"Sales Order: {sales_order}\nError: {str(e)}"
        )
        return {
            "exists": False,
            "can_create_po": False,
            "message": _("Error checking Pick List: {0}").format(str(e))
        }


@frappe.whitelist()
def test_get_pick_list_data(sales_order: str):
    """
    Test function to verify Pick List data extraction.
    Can be called from browser console for testing.
    
    Usage:
        frappe.call({
            method: 'kindlife_app.api.internal_transfer.test_get_pick_list_data',
            args: { sales_order: 'SO-00001' },
            callback: (r) => console.log(r.message)
        });
    """
    result = get_pick_list_batch_serial_data(sales_order)
    
    # Pretty print for testing
    if result.get("success"):
        frappe.msgprint({
            "title": _("Pick List Data Retrieved"),
            "message": f"""
                <b>Pick List:</b> {result.get('pick_list')}<br>
                <b>Items Found:</b> {len(result.get('data', {}))}<br><br>
                <pre>{frappe.as_json(result.get('data'), indent=2)}</pre>
            """,
            "indicator": "green"
        })
    else:
        frappe.msgprint({
            "title": _("Error"),
            "message": result.get("message"),
            "indicator": "red"
        })
    
    return result
