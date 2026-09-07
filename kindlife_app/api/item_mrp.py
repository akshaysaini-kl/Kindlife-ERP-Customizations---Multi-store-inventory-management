import frappe

@frappe.whitelist()
def create_item_mrp(item_code, new_mrp, effective_from):
    """
    Creates and submits an Item MRP document.
    """
    if not frappe.has_permission("Item MRP", "create"):
        frappe.throw(frappe._("Not permitted to create Item MRP"), frappe.PermissionError)
        
    doc = frappe.new_doc("Item MRP")
    doc.item_code = item_code
    doc.new_mrp = new_mrp
    doc.effective_from = effective_from
    doc.insert(ignore_permissions=True) # Checked permission above
    
    return doc.name


@frappe.whitelist()
def get_mrp_history(item_code):
    """
    Returns MRP history for the given item_code, ordered by effective date descending.
    """
    return frappe.get_all(
        "Item MRP", 
        filters={"item_code": item_code}, 
        fields=["name", "old_mrp", "new_mrp", "effective_from", "status", "owner", "creation", "docstatus"], 
        order_by="effective_from desc"
    )
