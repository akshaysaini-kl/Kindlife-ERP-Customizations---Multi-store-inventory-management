import frappe

def update_gst_hsn_code(doc):
    for item in doc.items:
        if not item.item_code or not item.gst_hsn_code:
            continue
        
        # Get existing gst_hsn_code from Item master
        item_gst_hsn = frappe.db.get_value("Item", item.item_code, "gst_hsn_code")

        # Trigger only if HSN entered in Purchase Invoice is different
        if item.gst_hsn_code == item_gst_hsn:
            continue  # No change, skip

        # Check if HSN exists in master
        gst_hsn_exists = frappe.db.exists("GST HSN Code", {"name": item.gst_hsn_code})
        if not gst_hsn_exists:
            # Create new GST HSN Code
            hsn_doc = frappe.new_doc("GST HSN Code")
            hsn_doc.hsn_code = item.gst_hsn_code
            hsn_doc.insert(ignore_permissions=True)
            frappe.msgprint(f"Created new GST HSN Code: <b>{item.gst_hsn_code}</b>")

        # Update Item master with the new/updated HSN code
        frappe.db.set_value("Item", item.item_code, "gst_hsn_code", item.gst_hsn_code)
        frappe.msgprint(f"Updated Item <b>{item.item_code}</b> with HSN Code <b>{item.gst_hsn_code}</b>")