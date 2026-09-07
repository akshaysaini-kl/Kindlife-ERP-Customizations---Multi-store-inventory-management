import frappe

@frappe.whitelist()
def get_draft_documents_count(purchase_order):
    """
    Get count of draft Purchase Receipts, Purchase Invoices, and Stock Entries for a Purchase Order
    Also returns all submitted documents with item details for display purposes
    Uses frappe.get_list to respect permission queries
    """
    if not purchase_order:
        return {
            "draft_pr_count": 0, 
            "draft_pi_count": 0,
            "all_pr_names": [],
            "all_pi_names": [],
            "all_se_data": []
        }
    
    # Get all Purchase Receipt Items linked to this PO
    pr_items = frappe.get_all(
        'Purchase Receipt Item',
        filters={'purchase_order': purchase_order},
        fields=['parent', 'item_code', 'item_name', 'qty', 'rejected_qty'],
        distinct=True
    )
    pr_names = [item.parent for item in pr_items]
    
    # Group PR items by parent
    pr_items_map = {}
    for item in pr_items:
        if item.parent not in pr_items_map:
            pr_items_map[item.parent] = []
        pr_items_map[item.parent].append({
            'item_code': item.item_code,
            'item_name': item.item_name,
            'accepted_qty': item.qty,
            'rejected_qty': item.rejected_qty or 0
        })
    
    # Get Purchase Receipts details (draft + submitted, exclude cancelled)
    all_pr_data = []
    draft_pr_names = []
    
    if pr_names:
        all_pr_data = frappe.get_list(
            'Purchase Receipt',
            filters={
                'name': ['in', pr_names],
                'docstatus': ['!=', 2]
            },
            fields=['name', 'status', 'docstatus','workflow_state'],
            order_by='creation desc'
        )
        
        # Add items to PR data
        for pr in all_pr_data:
            pr['items'] = pr_items_map.get(pr.name, [])
        
        # Filter draft PRs
        draft_pr_names = [pr.name for pr in all_pr_data if pr.docstatus == 0]
    
    # Get all Purchase Invoice Items linked to this PO
    pi_items = frappe.get_all(
        'Purchase Invoice Item',
        filters={'purchase_order': purchase_order},
        fields=['parent', 'item_code', 'item_name', 'qty', 'amount'],
        distinct=True
    )
    pi_names = [item.parent for item in pi_items]
    
    # Group PI items by parent
    pi_items_map = {}
    for item in pi_items:
        if item.parent not in pi_items_map:
            pi_items_map[item.parent] = []
        pi_items_map[item.parent].append({
            'item_code': item.item_code,
            'item_name': item.item_name,
            'qty': item.qty,
            'amount': item.amount
        })
    
    # Get Purchase Invoices details (draft + submitted, exclude cancelled)
    all_pi_data = []
    draft_pi_names = []
    
    if pi_names:
        try:
            all_pi_data = frappe.get_list(
                'Purchase Invoice',
                filters={
                    'name': ['in', pi_names],
                    'docstatus': ['!=', 2]
            },
                fields=['name', 'status', 'docstatus', 'posting_date', 'grand_total', 'is_return'],
                order_by='creation desc'
            )
            
            # Add items to PI data
            for pi in all_pi_data:
                pi['items'] = pi_items_map.get(pi.name, [])
            
            # Filter draft PIs
            draft_pi_names = [pi.name for pi in all_pi_data if pi.docstatus == 0]
        except frappe.exceptions.PermissionError as e:
            pass
    
    # Get Stock Entries linked to Purchase Receipts of this PO
    all_se_data = []
    if pr_names:
        try:
            # Get Stock Entry Details linked to PRs
            se_details = frappe.get_all(
                'Stock Entry Detail',
                filters={
                    'reference_purchase_receipt': ['in', pr_names]
                },
                fields=['parent', 'item_code', 'item_name', 's_warehouse', 't_warehouse', 'qty'],
                distinct=True
            )
            
            se_names = list(set([detail.parent for detail in se_details]))
            
            # Group SE items by parent
            se_items_map = {}
            for item in se_details:
                if item.parent not in se_items_map:
                    se_items_map[item.parent] = []
                se_items_map[item.parent].append({
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'from_warehouse': item.s_warehouse,
                    'to_warehouse': item.t_warehouse,
                    'qty': item.qty
                })
            
            if se_names:
                all_se_data = frappe.get_list(
                    'Stock Entry',
                    filters={
                        'name': ['in', se_names],
                        'docstatus': ['!=', 2]
                    },
                    fields=['name', 'stock_entry_type', 'docstatus'],
                    order_by='creation desc'
                )
                
                # Add items to SE data
                for se in all_se_data:
                    se['items'] = se_items_map.get(se.name, [])
                    se['status'] = 'Draft' if se.docstatus == 0 else 'Submitted'
                    
        except frappe.exceptions.PermissionError as e:
            pass
            
    return {
        "draft_pr_count": len(draft_pr_names),
        "draft_pi_count": len(draft_pi_names),
        "draft_pr_names": draft_pr_names,
        "draft_pi_names": draft_pi_names,
        "all_pr_data": all_pr_data,
        "all_pi_data": all_pi_data,
        "all_se_data": all_se_data
    }

@frappe.whitelist()
def get_items_by_supplier(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom query to filter items by supplier
    """
    supplier = filters.get('supplier')
    
    if not supplier:
        return []
    
    # Query to get items that have the supplier in their supplier_items table
    return frappe.db.sql("""
        SELECT DISTINCT 
            i.name, 
            i.item_name,
            i.item_group
        FROM 
            `tabItem` i
        INNER JOIN 
            `tabItem Supplier` si ON si.parent = i.name
        WHERE 
            si.supplier = %(supplier)s
            AND i.disabled = 0
            AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
        ORDER BY 
            i.name
        LIMIT %(start)s, %(page_len)s
    """, {
        'supplier': supplier,
        'txt': f"%{txt}%",
        'start': start,
        'page_len': page_len
    })
@frappe.whitelist()
def get_awb_number(so_name, item_code):
    """
    Server-side helper to fetch AWB Number from a Sales Order Item.
    Avoiding client-side frappe.db.get_value to bypass permission issues on child tables.
    """
    if not so_name or not item_code:
        return None
        
    awb_number = frappe.db.get_value("Sales Order Item", 
        {"parent": so_name, "item_code": item_code}, 
        "custom_awb_number"
    )
    
    return awb_number
