

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, GroupConcat, Coalesce
from pypika import Order

# Define status colors for color coding
STATUS_COLORS = {
    # Generic
    "Draft": "Black",
    "Submitted": "green",
    "Completed": "green",
    "Cancelled": "#d9534f",  # Red
    # Purchase Order specific
    "To Receive and Bill": "orange",
    "To Receive": "blue",
    "To Bill": "#DAA520",  # GoldenRod
    "Closed": "green",
    "On Hold": "#490455",
    # Purchase Receipt specific
    "Return Issued": "#d84ef0",  # Orange-yellow
    # Stock Entry specific
    "Pending": "orange",
    "Approved": "green",
    "Rejected": "#00ff84",
    "N/A": "darkgray",
    "Pending Scanning":"#107de4",
}

def execute(filters=None):
    columns = get_columns()
    # The client script is only run when the report is made, it wont be run when exporting
    # frappe.log_error(title="Report Execution Started", message=f"columns is {columns}")
    # frappe.log_error(title="Report Execution Started", message=f"frappe.flags.in_export is {frappe.flags.in_export}")
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "purchase_order", "label": _("Purchase Order"), "fieldtype": "Link", "options": "Purchase Order", "width": 180},
        {"label":"Item","fieldname":"item","fieldtype":"HTML","width":280},
        {"label":"Brand","fieldname":"brand","fieldtype":"Link","options":"Brand","width":120},
        {"label":"Item SKU","fieldname":"item_sku","fieldtype":"Data","width":140},
        {"label":"Qty","fieldname":"qty","fieldtype":"Float","width":80},

        {"fieldname": "po_date", "label": _("PO Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 180},
        {"fieldname": "po_status", "label": _("PO Status"), "fieldtype": "HTML", "width": 130},
        {"fieldname": "total_qty", "label": _("Total Qty"), "fieldtype": "Float", "width": 100},
        {"fieldname": "po_amount", "label": _("PO Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "pr_count", "label": _("PR Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "pr_numbers", "label": _("Purchase Receipts | Date | Status | Acc/Rej"), "fieldtype": "HTML", "width": 400},
        # {"fieldname": "pr_acc_rej", "label": _("Purchase Receipts(Acc/Rej)"), "fieldtype": "HTML", "width": 400},
        {"fieldname": "se_count", "label": _("SE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "se_numbers", "label": _("Stock Entries | Date | Status"), "fieldtype": "HTML", "width": 400},
        {"fieldname": "per_received", "label": _("% Received"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "per_billed", "label": _("% Billed"), "fieldtype": "Percent", "width": 100},
    ]


def get_data(filters):
    """Fetch PO tracking data using frappe.get_list for permission-aware queries"""
    
    # Build filters for Purchase Order
    po_filters = build_po_filters(filters)
    
    # Fetch Purchase Orders using get_list - this respects permission_query_conditions
    purchase_orders = frappe.get_list(
        "Purchase Order",
        filters=po_filters,
        fields=[
            "name",
            "transaction_date",
            "supplier",
            "status",
            "grand_total",
            "per_received",
            "per_billed",
            "total_qty"
        ],
        order_by="transaction_date desc, name",
        limit_page_length=0
    )
    
    if not purchase_orders:
        return []
    
    # Get PO names for fetching related data
    po_names = [po.name for po in purchase_orders]
    
    # Fetch PO Items using Query Builder (no permission needed for child tables)
    poi = DocType("Purchase Order Item")
    item = DocType("Item")
    
    po_items_query = (
        frappe.qb.from_(poi)
        .left_join(item).on(poi.item_code == item.name)
        .select(
            poi.name.as_("po_item_name"),
            poi.parent.as_("purchase_order"),
            poi.item_code,
            poi.item_name,
            poi.qty,
            item.brand
        )
        .where(poi.parent.isin(po_names))
    )
    
    # Apply item_code filter if specified
    if filters.get("item_code"):
        po_items_query = po_items_query.where(poi.item_code == filters.get("item_code"))
    
    po_items_data = po_items_query.run(as_dict=True)
    
    # Group items by PO
    items_by_po = {}
    for item in po_items_data:
        items_by_po.setdefault(item.purchase_order, []).append(item)
    
    if not items_by_po:
        return []
    
    # Get unique item codes for SKU lookup
    item_codes = list(set([item.item_code for items in items_by_po.values() for item in items if item.item_code]))
    
    # Fetch Item SKU data
    item_sku_map = get_item_sku_map(item_codes)
    
    # Fetch PR and SE data for these POs
    pr_data_map = get_pr_data_for_pos(po_names)
    
    # Extract unique PR names from pr_data_map
    all_pr_names = set()
    for pr_info in pr_data_map.values():
        all_pr_names.update(pr_info.get('pr_names_list', []))
    
    se_data_map = get_se_data_for_prs(list(all_pr_names))
    
    # Build parent-child structure
    final_data = []
    
    for po in purchase_orders:
        po_name = po.name
        items_for_po = items_by_po.get(po_name, [])
        
        if not items_for_po:
            continue
        
        # Aggregate PR and SE data at PO level
        po_pr_info = aggregate_po_pr_data(po_name, items_for_po, pr_data_map)
        po_se_info = aggregate_po_se_data(po_pr_info.get('all_pr_names', []), se_data_map)
        
        # Create parent row (PO level)
        parent_row = {
            "indent": 0,
            "parent": "",
            "is_group": 1,
            "purchase_order": po_name,
            "po_date": po.transaction_date,
            "supplier": po.supplier,
            "po_status": get_status_html(po.status),
            "po_amount": po.grand_total,
            "per_received": po.per_received,
            "per_billed": po.per_billed,
            "total_qty": po.total_qty,
            "pr_count": po_pr_info.get('pr_count', 0),
            "pr_numbers": po_pr_info.get('pr_links_html', ''),
            "pr_ui_details": po_pr_info.get('pr_ui_details', []),
            "se_count": po_se_info.get('se_count', 0),
            "se_numbers": po_se_info.get('se_links_html', ''),
            "se_ui_details": po_se_info.get('se_ui_details', []),
            "item": "",
            "brand": "",
            "item_sku": "",
            "qty": None
        }
        final_data.append(parent_row)
        
        # Create child rows (Item level)
        for item_row in items_for_po:
            item_code = item_row.item_code
            item_name = item_row.item_name
            display_text = f"{item_code}: {item_name}" if item_name else item_code
            item_link_html = f'<a href="/app/item/{item_code}" target="_blank">{display_text}</a>'

            # STEP 1: Get the PR data for THIS specific item first
            pr_key = (po_name, item_row.po_item_name, item_code)
            pr_info = pr_data_map.get(pr_key, {})

            # Here we have got list of all PRs connected to particular item.
            # We made multiple lists and saved the information different information of pr in each list
            pr_links_list = [] 
            pr_hidden_details_list = []
            pr_names_list = pr_info.get('pr_names_list', [])
            pr_status_list = pr_info.get('pr_status_list', [])
            pr_dates_list = pr_info.get('pr_dates_list', [])
            accepted_qtys = pr_info.get('accepted_qtys', [])
            rejected_qtys = pr_info.get('rejected_qtys', [])

            # Here we iterate over each PR and make combined string for HTML for each PR
            # We use enumerate to get index of each iteration
            for i, pr_name in enumerate(pr_names_list):
                status = pr_status_list[i]
                date = pr_dates_list[i]
                color = STATUS_COLORS.get(status, "#00ff84")
                accepted = accepted_qtys[i]
                rejected = rejected_qtys[i]


                link_html = f'<a href="/app/purchase-receipt/{pr_name}" target="_blank" ">{pr_name}</a>'
                export_string = f"{pr_name} ({accepted} / {rejected})"

                pr_links_list.append(f"{export_string}")

                status_html = f'<span style="color:{color};">{status}</span>'
                qty_html = f'{accepted} / {rejected}'


                pr_hidden_details_list.append({"link_html": link_html,"date": date,"status_html": status_html,"qty_html": qty_html})

            item_pr_details_html = "\n".join(pr_links_list)
            
            # Get SE data for this item's PRs
            pr_names = pr_info.get('pr_names_list', [])
            se_links_list = []
            se_hidden_details_list = []

            all_ses = []
            seen_ses = set()
            # Here we make list of all data of the SEs
            # THis loop is to make sure that each SE comes only once.
            for pr_name in pr_names:
                if pr_name in se_data_map:
                    for se in se_data_map[pr_name]:
                        if se['name'] not in seen_ses:
                            all_ses.append(se)
                            seen_ses.add(se['name'])
            all_ses.sort(key=lambda x: x['posting_date']) # Sort them

            for se in all_ses:
                se_name = se['name']
                workflow = se['workflow_state']
                date = se['posting_date'].strftime("%d-%m-%Y") if se['posting_date'] else ""

                # 1. Create the link for the se_numbers (export) column
                se_link_html = f'<a href="/app/stock-entry/{se_name}" target="_blank">{se_name}</a>'
                export_string = f"{se_name}"
                se_links_list.append(f"{export_string}")

                # 2. Create a dictionary with extra details for the hidden UI column
                workflow_html = f'<span style="color:{STATUS_COLORS.get(workflow, "#00ff84")};">{workflow}</span>'
                se_hidden_details_list.append({
                    "link_html": se_link_html, 
                    "date": date,
                    "workflow_html": workflow_html
                })

            item_se_details_html = "\n".join(se_links_list)

            child_row = {
                "indent": 1,
                "parent": po_name,
                "is_group": 0,
                "item": item_link_html,
                "brand": item_row.brand,
                "item_sku": item_sku_map.get(item_code, ''),
                "qty": item_row.qty,
                "pr_numbers": item_pr_details_html,
                "se_numbers": item_se_details_html,
                # "pr_acc_rej":pr_hidden_details_list.get("qty_html"),
                "pr_ui_details": pr_hidden_details_list,
                "se_ui_details": se_hidden_details_list,
                # Empty fields for child rows
                "purchase_order": "",
                "po_date": None,
                "supplier": "",
                "po_status": "",
                "po_amount": None,
                "per_received": None,
                "per_billed": None,
                "total_qty": None,
                "pr_count": None,
                "pr_dates": "",
                "pr_status": "",
                "pr_workflow_state": "",
                "se_count": None,
                "se_dates": "",
                "se_status": "",
                "se_workflow_state": ""
            }
            final_data.append(child_row)
    
    return final_data


def build_po_filters(filters):
    """Build filters for Purchase Order get_list"""
    po_filters = {"docstatus": ["in", [0, 1]]}
    
    # Handle date range filters
    if filters.get("from_date") and filters.get("to_date"):
        po_filters["transaction_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
    elif filters.get("from_date"):
        po_filters["transaction_date"] = [">=", filters.get("from_date")]
    elif filters.get("to_date"):
        po_filters["transaction_date"] = ["<=", filters.get("to_date")]
    
    if filters.get("supplier"):
        po_filters["supplier"] = filters.get("supplier")
    
    if filters.get("purchase_order"):
        po_filters["name"] = filters.get("purchase_order")
    
    if filters.get("status"):
        po_filters["status"] = filters.get("status")
    
    return po_filters


def get_item_sku_map(item_codes):
    """Fetch first supplier part number for each item"""
    if not item_codes:
        return {}
    
    item_supplier = DocType("Item Supplier")
    
    # Get first supplier part number for each item
    sku_data = (
        frappe.qb.from_(item_supplier)
        .select(item_supplier.parent, item_supplier.supplier_part_no)
        .where(item_supplier.parent.isin(item_codes))
        .where(item_supplier.supplier_part_no.isnotnull())
        .orderby(item_supplier.parent)
        .orderby(item_supplier.idx)
    ).run(as_dict=True)
    
    # Get first SKU for each item
    sku_map = {}
    for row in sku_data:
        if row.parent not in sku_map:
            sku_map[row.parent] = row.supplier_part_no
    
    return sku_map


def get_pr_data_for_pos(po_names):
    """Fetch Purchase Receipt data for given POs"""
    if not po_names:
        return {}
    
    pri = DocType("Purchase Receipt Item")
    pr = DocType("Purchase Receipt")
    
    pr_data = (
        frappe.qb.from_(pri)
        .left_join(pr).on(pri.parent == pr.name)
        .select(
            pri.purchase_order,
            pri.purchase_order_item,
            pri.item_code,
            pr.name.as_("pr_name"),
            pr.posting_date,
            pr.status,
            pri.qty,
            pri.rejected_qty,

        )
        .where(pri.purchase_order.isin(po_names))
        .where(pr.docstatus != 2)
        .orderby(pr.posting_date)
    ).run(as_dict=True)
    
    # Group by PO item
    pr_map = {}
    for row in pr_data:
        key = (row.purchase_order, row.purchase_order_item, row.item_code)
        if key not in pr_map:
            pr_map[key] = {
                'pr_names': [],
                'pr_names_list': [],
                'pr_dates': [],
                'pr_status': [],
                'pr_workflow_state': [],
                'pr_count': 0,
                'accepted_qtys': [],
                'rejected_qtys': []

            }
        
        if row.pr_name and row.pr_name not in pr_map[key]['pr_names']:
            pr_map[key]['pr_names'].append(row.pr_name)
            pr_map[key]['pr_names_list'].append(row.pr_name)
            pr_map[key]['pr_dates'].append(row.posting_date.strftime("%d-%m-%Y") if row.posting_date else "")
            pr_map[key]['pr_status'].append(row.status or "N/A")
            pr_map[key]['pr_workflow_state'].append(row.workflow_state or "N/A")
            pr_map[key]['pr_count'] += 1
            pr_map[key]['accepted_qtys'].append(row.qty or 0)
            pr_map[key]['rejected_qtys'].append(row.rejected_qty or 0)

    
    # Convert lists to comma-separated strings and keep status lists
    for key in pr_map:
        pr_map[key]['pr_dates_list'] = pr_map[key]['pr_dates'] 
        pr_map[key]['pr_status_list'] = pr_map[key]['pr_status']
        pr_map[key]['pr_status'] = ', '.join(pr_map[key]['pr_status'])
        pr_map[key]['pr_workflow_state'] = ', '.join(pr_map[key]['pr_workflow_state'])
    
    return pr_map


def get_se_data_for_prs(pr_names):
    """Fetch Stock Entry data for given PRs"""
    if not pr_names:
        return {}
    
    sed = DocType("Stock Entry Detail")
    se = DocType("Stock Entry")
    
    se_data = (
        frappe.qb.from_(sed)
        .left_join(se).on(sed.parent == se.name)
        .select(
            sed.reference_purchase_receipt,
            se.name.as_("se_name"),
            se.posting_date,
            se.docstatus,
            se.workflow_state
        )
        .where(sed.reference_purchase_receipt.isin(pr_names))
        .where(se.docstatus != 2)
        .orderby(se.posting_date)
    ).run(as_dict=True)
    
    # Group by PR
    se_map = {}
    for row in se_data:
        pr_name = row.reference_purchase_receipt
        if pr_name not in se_map:
            se_map[pr_name] = []
        
        if row.se_name:
            se_map[pr_name].append({
                'name': row.se_name,
                'posting_date': row.posting_date,
                'docstatus': row.docstatus,
                'workflow_state': row.workflow_state
            })
    
    return se_map


def aggregate_se_data(pr_names, se_data_map):
    """Aggregate SE data for multiple PRs"""
    all_ses = []
    seen_ses = set()
    
    for pr_name in pr_names:
        if pr_name in se_data_map:
            for se in se_data_map[pr_name]:
                if se['name'] not in seen_ses:
                    all_ses.append(se)
                    seen_ses.add(se['name'])
    
    if not all_ses:
        return {
            'se_count': 0,
            'se_numbers': '',
            'se_dates': '',
            'se_status': '',
            'se_workflow_state': ''
        }
    
    # Sort by posting date
    all_ses.sort(key=lambda x: x['posting_date'])
    
    return {
        'se_count': len(all_ses),
        'se_numbers': ', '.join([se['name'] for se in all_ses]),
        'se_dates': ', '.join([se['posting_date'].strftime("%d-%m-%Y") if se['posting_date'] else "" for se in all_ses]),
        'se_status': ', '.join([get_se_status(se['docstatus']) for se in all_ses]),
        'se_workflow_state': ', '.join([se['workflow_state'] or "N/A" for se in all_ses])
    }


def get_se_status(docstatus):
    """Convert docstatus to status string"""
    if docstatus == 0:
        return "Draft"
    elif docstatus == 1:
        return "Submitted"
    elif docstatus == 2:
        return "Cancelled"
    else:
        return "N/A"


def get_status_html(status):
    """Wrap status in colored HTML"""
    if not status:
        return ""
    color = STATUS_COLORS.get(status, "#00ff84")
    return f'<div style="color: {color};">{status}</div>'


def aggregate_po_pr_data(po_name, items_for_po, pr_data_map):
    """Aggregate PR data at PO level from all items"""
    all_prs = {}  # {pr_name: {status, workflow_state, date}}
    all_pr_names = []
    
    for item in items_for_po:
        pr_key = (po_name, item.po_item_name, item.item_code)
        pr_info = pr_data_map.get(pr_key, {})
        
        pr_names = pr_info.get('pr_names_list', [])
        pr_statuses = pr_info.get('pr_status', '').split(', ')
        pr_workflows = pr_info.get('pr_workflow_state', '').split(', ')
        pr_dates = pr_info.get('pr_dates_list', [])
        
        for i, pr_name in enumerate(pr_names):
            if pr_name and pr_name not in all_prs:
                all_prs[pr_name] = {
                    'status': pr_statuses[i] if i < len(pr_statuses) else 'N/A',
                    'workflow_state': pr_workflows[i] if i < len(pr_workflows) else 'N/A',
                    'date': pr_dates[i] if i < len(pr_dates) else ''
                }
                all_pr_names.append(pr_name)
    
    if not all_prs:
        return {
            'pr_count': 0,
            'pr_links_html': '',
            'pr_ui_details': [],
            'all_pr_names': []
        }
    
    # Create colored HTML for links
    pr_links_list = []
    pr_ui_details_list = []
    
    for pr_name, pr_data in all_prs.items():
        status = pr_data['status']
        date = pr_data['date']
        color = STATUS_COLORS.get(status, "#00ff84")
        
        link_html_tag = f'<a href="/app/purchase-receipt/{pr_name}" target="_blank">{pr_name}</a>'
        pr_links_list.append(f"<div>{link_html_tag}</div>")

        status_html = f'<span style="color:{color};">{status}</span>'
        pr_ui_details_list.append({
            "link_html":link_html_tag,
            "date": date,
            "status_html": status_html,
            "qty_html": "" 
        })

    
    return {
        'pr_count': len(all_prs),
        'pr_links_html': "\n".join(pr_links_list),
        'pr_ui_details': pr_ui_details_list,
        'all_pr_names': all_pr_names
    }


def aggregate_po_se_data(pr_names, se_data_map):
    """Aggregate SE data at PO level from all PRs"""
    all_ses = {}  # {se_name: {docstatus, workflow_state, date}}
    
    for pr_name in pr_names:
        if pr_name in se_data_map:
            for se in se_data_map[pr_name]:
                se_name = se['name']
                if se_name not in all_ses:
                    all_ses[se_name] = se
    
    if not all_ses:
        return { 'se_count': 0, 'se_links_html': '', 'se_ui_details': [] }
    # Sort by posting date
    sorted_ses = sorted(all_ses.values(), key=lambda x: x['posting_date'])
    se_links_list = []
    se_ui_details_list = []
    
    
    for se in sorted_ses:
        se_name = se['name']
        workflow = se['workflow_state'] or 'N/A'
        date = se['posting_date'].strftime("%d-%m-%Y") if se['posting_date'] else ""
        
        link_html_tag = f'<a href="/app/stock-entry/{se_name}" target="_blank">{se_name}</a>'
        se_links_list.append(f"<div>{link_html_tag}</div>")

        workflow_html = f'<span style="color:{STATUS_COLORS.get(workflow, "Orange")};">{workflow}</span>'

        se_ui_details_list.append({"link_html":link_html_tag,"date": date,"workflow_html": workflow_html})
    
    return {
        'se_count': len(all_ses),
        'se_links_html': "\n".join(se_links_list),
        'se_ui_details': se_ui_details_list
    }


