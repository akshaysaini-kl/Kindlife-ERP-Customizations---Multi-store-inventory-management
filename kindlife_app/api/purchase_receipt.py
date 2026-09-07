import frappe
import json
from frappe.utils import flt
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_return
from kindlife_app.api.purchase_return_service import PurchaseReturnService


@frappe.whitelist()
def get_draft_stock_entries_count(purchase_receipt):
    """
    Get count of draft Stock Entries (Putaway) for a Purchase Receipt
    Also returns all Stock Entries with status for display
    Uses frappe.get_list to respect permission queries
    """
    if not purchase_receipt:
        return {
            "draft_se_count": 0, 
            "draft_se_names": [],
            "all_se_data": []
        }
    
    # Get all Stock Entry Detail items linked to this PR
    se_items = frappe.get_all(
        'Stock Entry Detail',
        filters={
            'reference_purchase_receipt': purchase_receipt
        },
        fields=['parent'],
        distinct=True
    )
    se_names = [item.parent for item in se_items]
    
    # Get Stock Entries details (draft + submitted, exclude cancelled)
    all_se_data = []
    draft_se_names = []
    
    if se_names:
        all_se_data = frappe.get_list(
            'Stock Entry',
            filters={
                'name': ['in', se_names],
                'docstatus': ['!=', 2],
                'purpose': 'Material Transfer'
            },
            fields=['name', 'stock_entry_type', 'docstatus'],
            order_by='creation desc'
        )
        
        # Filter draft SEs
        draft_se_names = [se.name for se in all_se_data if se.docstatus == 0]
    
    # Get transferred quantities per item from submitted Stock Entries
    # For this we need to use get_list with aggregation via SQL as frappe.get_list doesn't support GROUP BY aggregation
    # But we'll filter by the SE names we already have permission to see
    transferred_qty = {}
    
    if se_names:
        # Get submitted SE names only
        submitted_se_names = [se.name for se in all_se_data if se.docstatus == 1]
        
        if submitted_se_names:
            # Get all items from submitted SEs
            transferred_items = frappe.get_all(
                'Stock Entry Detail',
                filters={
                    'parent': ['in', submitted_se_names],
                    'reference_purchase_receipt': purchase_receipt,
                    's_warehouse': ['is', 'set']
                },
                fields=['item_code', 'qty']
            )
            
            # Aggregate quantities per item
            for item in transferred_items:
                if item.item_code in transferred_qty:
                    transferred_qty[item.item_code] += item.qty
                else:
                    transferred_qty[item.item_code] = item.qty
    
    return {
        "draft_se_count": len(draft_se_names),
        "draft_se_names": draft_se_names,
        "all_se_data": all_se_data,
        "transferred_qty": transferred_qty
    }


@frappe.whitelist()
def get_warehouses_from_delivery_note(delivery_note):
    """
    API for client-side script to fetch default warehouses for internal Purchase Receipt 
    based on the source Delivery Note and its linked Sales Order.
    """
    if not frappe.has_permission("Purchase Receipt", "write"):
        frappe.throw("Not permitted", frappe.PermissionError)
        
    dn = frappe.get_doc("Delivery Note", delivery_note)
    
    result = {
        "set_from_warehouse": dn.set_target_warehouse,
        "set_warehouse": None,
        "rejected_warehouse": None
    }

    sales_order = None
    for item in dn.items:
        if item.against_sales_order:
            sales_order = item.against_sales_order
            break

    if sales_order:
        so_custom_destination_warehouse = frappe.db.get_value("Sales Order", sales_order, "custom_destination_warehouse")
        if so_custom_destination_warehouse:
            qc_warehouse = frappe.db.get_value("Warehouse", 
                {"parent_warehouse": so_custom_destination_warehouse, "custom_is_qc_warehouse": 1}, 
                "name"
            )
            if qc_warehouse:
                result["set_warehouse"] = qc_warehouse

            rejected_warehouse = frappe.db.get_value("Warehouse", 
                {"parent_warehouse": so_custom_destination_warehouse, "is_rejected_warehouse": 1}, 
                "name"
            )
            if rejected_warehouse:
                result["rejected_warehouse"] = rejected_warehouse

    print(result)
    return result





# ----------------------------Code for purchase return ----------------------------
@frappe.whitelist()
def get_return_context(pr_name):
    """
    Single API to fetch EVERYTHING needed for the Frontend:
    1. scan_map: { barcode: group_key } for fast lookup
    2. groups: { group_key: { metadata, all_serials_list } } for row creation/filling
    """
    service = PurchaseReturnService(pr_name)
    return {
        "scan_map": service.get_scanner_map(),
        "groups": service.get_grouped_data()
    }

@frappe.whitelist()
def make_custom_purchase_return(source_name):
    """
    Creates the Return Doc and pre-fills rows based on initial logic:
    - Rejected: Filled completely
    - Accepted: Empty (Qty 0)
    """

    service = PurchaseReturnService(source_name)
    groups = service.get_grouped_data()

    if not groups:
        frappe.throw("No returnable active serials found.")

    source_doc = frappe.get_doc("Purchase Receipt", source_name)
    doc = frappe.new_doc("Purchase Receipt")
    
    doc.is_return = 1
    doc.return_against = source_name
    doc.supplier = source_doc.supplier
    doc.company = source_doc.company
    doc.posting_date = frappe.utils.today()
    doc.set_warehouse = "" 

    # Initial Table Population
    for key, data in groups.items():
        _add_row_to_doc(doc, data)

    return doc


def _add_row_to_doc(doc, data):
    """
    Helper to append a row.
    """
    row = doc.append("items", {})

    # Static Data
    row.item_code = data['item_code']
    row.item_name = data['item_name']
    row.warehouse = data['warehouse']
    row.batch_no = data['batch_no']
    row.purchase_receipt_item = data['pr_item_name']
    row.rate = data['rate']
    row.uom = data['uom']
    row.stock_uom = data['stock_uom']
    row.conversion_factor = data['conversion_factor']
    
    # Custom Read-only info
    row.custom_total_returnable_qty = len(data['serials'])
    
    # Logic for Serials & Qty
    # Condition: It is Rejected OR we are forcing fill (Fill All button)
    should_fill = data['is_rejected_origin']

    if should_fill:
        row.serial_no = "\n".join(data['serials'])
        row.qty = -1 * len(data['serials'])
    else:
        row.serial_no = ""
        row.qty = 0

    # Dependent Fields
    row.return_qty_from_rejected_warehouse = 1 if data['is_rejected_origin'] else 0
    row.received_qty = row.qty
    row.stock_qty = row.qty * (row.conversion_factor or 1)
    row.use_serial_batch_fields = 1
    row.rejected_qty = 0
    row.rejected_warehouse = None
    
    return row



# Validate that none of connected SE are have unfinished scanning
def purchase_return_on_submit(doc, method):
    """
    Validates that Serial Numbers being returned are not locked 
    inside a Stock Entry that is 'Pending Scanning'.
    """
    # 1. Only run for Purchase Returns
    if not doc.is_return:
        return

    # 2. Collect all Serial Numbers from the current Purchase Return
    serials_to_check = []
    
    for row in doc.items:
        # Check Accepted Serials
        if row.serial_no:
            serials_to_check.extend([s.strip() for s in row.serial_no.replace(',', '\n').split('\n') if s.strip()])
            
        # Check Rejected Serials
        if row.rejected_serial_no:
            serials_to_check.extend([s.strip() for s in row.rejected_serial_no.replace(',', '\n').split('\n') if s.strip()])

    if not serials_to_check:
        return

    # 3. Query for conflicting Stock Entries (Name + Serial No)
    # Check 'workflow_state'.
    conflicts = frappe.db.sql("""
        SELECT DISTINCT se.name, entry.serial_no
        FROM `tabStock Entry` se
        JOIN `tabSerial and Batch Bundle` sabb ON sabb.voucher_no = se.name
        JOIN `tabSerial and Batch Entry` entry ON entry.parent = sabb.name
        WHERE
            se.docstatus = 1
            AND se.workflow_state = 'Pending Scanning' 
            AND entry.serial_no IN %(serials)s
    """, {'serials': serials_to_check}, as_dict=True)

    # 4. If conflicts found, Format the Error Message
    if conflicts:
        # Group by Stock Entry: { 'SE-001': ['SN1', 'SN2'], ... }
        grouped_conflicts = {}
        for c in conflicts:
            if c.name not in grouped_conflicts:
                grouped_conflicts[c.name] = []
            grouped_conflicts[c.name].append(c.serial_no)

        # Build HTML Table
        table_rows = ""
        for se_name, sn_list in grouped_conflicts.items():
            # Join serials with comma, limit to 5 for display if list is huge
            display_serials = ", ".join(sn_list[:5])
            if len(sn_list) > 5:
                display_serials += f" (+{len(sn_list)-5} more)"

            table_rows += f"""
                <tr>
                    <td><a href="/app/stock-entry/{se_name}" target="_blank"><b>{se_name}</b></a></td>
                    <td>{display_serials}</td>
                </tr>
            """

        msg = f"""
        <h5>Cannot Submit Purchase Return</h5>
        <p>The following Serial Numbers are currently locked in Stock Entries 
        that are marked as <b>Pending Scanning</b>.</p>
        
        <p>Please complete the scanning or cancel these entries first:</p>
        
        <table class="table table-bordered table-striped" style="font-size: 12px;">
            <thead>
                <tr>
                    <th width="40%">Stock Entry</th>
                    <th width="60%">Conflicting Serials</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        """
        
        frappe.throw(msg, title="Validation Error")

