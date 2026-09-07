import frappe

@frappe.whitelist()
def get_purchase_order_from_receipt(purchase_receipt, item_code):
    """
    Get Purchase Order linked to a Purchase Receipt for a specific item
    Uses frappe.get_list to respect permission queries
    """
    if not purchase_receipt or not item_code:
        return {"purchase_order": None}
    
    try:
        # Get Purchase Receipt Item with linked Purchase Order
        pr_items = frappe.get_all(
            'Purchase Receipt Item',
            filters={
                'parent': purchase_receipt,
                'item_code': item_code
            },
            fields=['purchase_order'],
            limit=1
        )
        
        if pr_items and pr_items[0].purchase_order:
            return {"purchase_order": pr_items[0].purchase_order}
        else:
            return {"purchase_order": None}
            
    except frappe.exceptions.PermissionError:
        # If user doesn't have permission to access Purchase Receipt Item
        return {"purchase_order": None}
    except Exception as e:
        frappe.log_error(f"Error getting Purchase Order from Receipt: {str(e)}")
        return {"purchase_order": None}
