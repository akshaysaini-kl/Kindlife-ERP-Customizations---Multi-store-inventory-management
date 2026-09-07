import frappe
from kindlife_app.utils.shipment_utils import sync_shipment_docs_for_doc

def validate(doc, method=None):
    set_source_warehouse_from_so(doc)
    set_transit_warehouse(doc)
    
    if doc.set_target_warehouse:
        for item in doc.items:
            if not item.target_warehouse:
                item.target_warehouse = doc.set_target_warehouse

    validate_missing_batch_numbers(doc)
    sync_shipment_docs_for_doc(doc, "against_sales_order")


def validate_missing_batch_numbers(doc):
    from frappe import _
    missing_batches = []
    
    for item in doc.items:
        if not item.batch_no:
            has_batch_no = frappe.get_cached_value("Item", item.item_code, "has_batch_no")
            if has_batch_no:
                missing_batches.append(item)
            
    if missing_batches:
        msg = _("The following items require a Batch Number but none was provided:")
        
        # Build HTML table for the error message
        html = "<table class='table table-bordered' style='margin-top: 10px;'>"
        html += "<thead><tr><th>Row Number</th><th>Item Code</th><th>Warehouse</th></tr></thead><tbody>"
        
        for item in missing_batches:
            html += f"<tr><td>{item.idx}</td><td>{item.item_code}</td><td>{item.warehouse}</td></tr>"
            
        html += "</tbody></table>"
        
        frappe.throw(msg + html, title=_("Missing Batch Numbers"))


def set_source_warehouse_from_so(doc):
    """
    If created via Pick List, the set_warehouse might be missing.
    We fetch it from the linked Sales Order if available.
    """
    # if not doc.set_warehouse:
    for item in doc.items:
        if item.against_sales_order:
            so_warehouse = frappe.db.get_value("Sales Order", item.against_sales_order, "set_warehouse")
            print("so_warehouse",so_warehouse)
            if so_warehouse:
                doc.set_warehouse = so_warehouse
                break

def set_transit_warehouse(doc):
    """
    Automatically set set_target_warehouse from the shipping address.
    """
    if doc.set_target_warehouse:
        return

    # Fallback: If shipping_address_name is missing (e.g. created from PL), 
    # try to get it from the linked Sales Order
    address = doc.shipping_address_name
    if not address:
        for item in doc.items:
            if item.against_sales_order:
                address = frappe.db.get_value("Sales Order", item.against_sales_order, "shipping_address_name")
                if address: break

    if address:
        res = get_warehouses_from_address(address)
        if res and res.get("transit_warehouse"):
            doc.set_target_warehouse = res["transit_warehouse"]

@frappe.whitelist()
def get_warehouses_from_address(address):
    """
    Fetch the transit warehouse linked to an address.
    """
    if not address:
        return None
        
    linked_warehouse = frappe.db.get_value(
        "Dynamic Link", 
        {"parent": address, "parenttype": "Address", "link_doctype": "Warehouse"}, 
        "link_name"
    )
    
    transit_warehouse = None
    if linked_warehouse:
        # Fetch the transit (child) warehouse linked to this parent warehouse
        transit_warehouse = frappe.db.get_value(
            "Warehouse", 
            {
                "parent_warehouse": linked_warehouse, 
                "is_group": 0,
                "warehouse_type": "Transit"
            }, 
            "name"
        )
        
    return {
        "dispatch_warehouse": linked_warehouse,
        "transit_warehouse": transit_warehouse
    }
