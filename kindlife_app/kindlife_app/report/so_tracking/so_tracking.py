# sales_order_tracking_report_indent.py
import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, GroupConcat, Coalesce, Sum
from pypika import Order

# Define valid statuses and their colors centrally
# This makes it easy to manage and ensures consistency
VALID_STATUSES = {
    "Pick List": ["Open", "Completed", "Partly Delivered"],
    "Delivery Note": ["Draft", "To Bill", "Completed", "Return Issued", "Closed"],
    "Sales Invoice": [
        "Draft", "Return", "Credit Note Issued", "Submitted", "Paid", "Partly Paid",
        "Unpaid", "Unpaid and Discounted", "Partly Paid and Discounted",
        "Overdue and Discounted", "Overdue", "Internal Transfer"
    ],
}

STATUS_COLORS = {
    # Generic
    "Draft": "Black",
    "Open": "blue",
    "Completed": "green",
    "Paid": "green",
    "Closed": "green",
    "Cancelled": "#d9534f", # Red
    # Specific
    "To Deliver and Bill": "orange",
    "To Bill": "#DAA520", # GoldenRod
    "To Deliver": "blue",   
    "Partly Delivered": "purple",
    "Return Issued": "#f0ad4e", # Orange-yellow
    "Unpaid": "#DAA520",
    "Overdue": "#d9534f", # Red
    "Return": "#f0ad4e",
    "On Hold": "#d84ef0",
    "Pending Scanning":"#107de4",
}

def get_columns():
    return [
        {"fieldname": "sales_order", "label": _("Sales Order"), "fieldtype": "Link", "options": "Sales Order", "width": 190},
        {"fieldname": "po_no", "label": _("Buyer's PO"), "fieldtype": "Data", "width": 115},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 150},
        {"fieldname": "workflow_state", "label": _("SO Workflow Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "so_date", "label": _("SO Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "so_amount", "label": _("SO Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "item", "label": _("Item"), "fieldtype": "HTML", "width": 150},
        {"fieldname": "item_sku", "label": _("Item SKU"), "fieldtype": "Data", "width": 146},

        {"fieldname": "ordered_qty", "label": _("Ordered Qty"), "fieldtype": "int", "width": 80},
        {"fieldname": "picked_qty", "label": _("Picked Qty"), "fieldtype": "int", "width": 80},
        {"fieldname": "delivered_qty", "label": _("Delivered Qty"), "fieldtype": "int", "width": 80},
        {"fieldname": "pl_count", "label": _("PL Count"), "fieldtype": "Int", "width": 80},
        {"fieldname": "pick_lists", "label": _("Pick Lists | Date | Warehouse | Status"), "fieldtype": "HTML", "width": 510},

        {"fieldname": "dn_count", "label": _("DN Count"), "fieldtype": "Int", "width": 80},
        {"fieldname": "delivery_notes", "label": _("Delivery Notes | Date | Status"), "fieldtype": "HTML", "width": 310},
        {"fieldname": "si_count", "label": _("SI Count"), "fieldtype": "Int", "width": 80},
        {"fieldname": "sales_invoices", "label": _("Sales Invoices | Date | Status"), "fieldtype": "HTML", "width": 330},
        {"fieldname": "si_amount", "label": _("SI Amount"), "fieldtype": "Currency", "width": 120},
    ]



def execute(filters=None):
    if filters is None:
        filters = {}

    columns = get_columns()
    # so_rows, pl_data_map, dn_data_map, si_data_map = get_so_level_data(filters)
    so_list, pl_data_map, dn_data_map, si_data_map, so_item_map = get_so_level_data(filters)

    so_names = [r.name for r in so_list] if so_list else []
    items_by_so = {}
    if so_names:
        item_rows = get_item_level_data(so_names)
        for it in item_rows:
            items_by_so.setdefault(it['sales_order'], []).append(it)

    data = []
    for so in so_list:
        so_name = so.name

        # Process combined info strings into colored HTML
        pl_data = pl_data_map.get(so_name, {})
        dn_data = dn_data_map.get(so_name, {})
        si_data = si_data_map.get(so_name, {})

        parent_row = {
            "indent": 0,
            "parent": "",
            "is_group": 1,
            "sales_order": so_name,
            "customer": so.customer,
            "po_no": so.get("po_no"),
            "so_status": get_status_html(so.get("so_status")),
            "workflow_state": so.get("workflow_state"),

            "ordered_qty": so.ordered_qty,
            "picked_qty": so.picked_qty,
            "delivered_qty": so.delivered_qty,
            "pick_lists": pl_data.get("pl_for_export", ""),
            "pl_ui_details": pl_data.get("pl_ui_details", []),

            "delivery_notes": dn_data.get("dn_for_export", ""),
            "dn_ui_details": dn_data.get("dn_ui_details", []),

            "sales_invoices": si_data.get("si_for_export", ""),
            "si_ui_details": si_data.get("si_ui_details", []),

            "so_amount": so.grand_total,
            "si_amount": si_data.get("si_amount", 0),
            
			"so_date": so.transaction_date,



            
            "pl_count": pl_data.get("pl_count", 0),
            "dn_count": dn_data.get("dn_count", 0),
            "si_count": si_data.get("si_count", 0),
            "item": "",
			"item_sku": ""
        }
        data.append(parent_row)

        for it in items_by_so.get(so_name, []):

            item_code = it.get("item_code")
            item_name = it.get("item_name")
            display_text = f"{item_code} - {item_name}" if item_name else item_code
            item_link_html = f'<a href="/app/item/{item_code}" target="_blank">{display_text}</a>'
            
            pl_details_str = it.get('pl_details')
            item_pl_for_export_list, item_pl_ui_details_list = parse_item_details(pl_details_str, 'pick-list', has_warehouse=True)

            dn_details_str = it.get('dn_details')
            item_dn_for_export_list, item_dn_ui_details_list = parse_item_details(dn_details_str, 'delivery-note')

            si_details_str = it.get('si_details')
            item_si_for_export_list, item_si_ui_details_list = parse_item_details(si_details_str, 'sales-invoice')


            child_row = {
                "indent": 1,
                "parent": so_name,
                "is_group": 0,
                "item": item_link_html,
                "item_sku": it.get("item_sku"),

                "ordered_qty": it.get("ordered_qty"),
                "picked_qty": it.get("picked_qty"),
                "delivered_qty": it.get("delivered_qty"),
                "pick_lists": ", ".join(item_pl_for_export_list),
                "pl_ui_details": item_pl_ui_details_list,
                
                "delivery_notes": ", ".join(item_dn_for_export_list),
                "dn_ui_details": item_dn_ui_details_list,

                "sales_invoices": ", ".join(item_si_for_export_list),
                "si_ui_details": item_si_ui_details_list,

                "sales_order": "", "customer": "", "po_no": "", "so_status": "", "workflow_state": "", 
                "so_date": None, 
                "so_amount": None, "si_amount": None,
                "pl_count": None,
                "dn_count": None,
                "si_count": None,
            }
            data.append(child_row)

    return columns, data


def get_status_html(status):
    if not status: return ""
    color = STATUS_COLORS.get(status, "#00ff84")
    return f'<div style="color: {color};">{status}</div>'

def get_so_level_data(filters):
    """Fetch SO tracking data using frappe.get_list for permission-aware queries"""
    
    # Build filters for Sales Order
    so_filters = build_so_filters(filters)
    
    # Fetch Sales Orders using get_list - this respects permission_query_conditions
    sales_orders = frappe.get_list(
        "Sales Order",
        filters=so_filters,
        fields=[
            "name",
            "transaction_date",
            "customer",
            "status",
            "workflow_state",
            "po_no",
            "grand_total",
            "total_qty",
            "delivery_date"
        ],
        order_by="transaction_date desc, name",
        limit_page_length=0
    )
    
    if not sales_orders:
        return []
    
    # Get SO names for fetching related data
    so_names = [so.name for so in sales_orders]
    
    # Fetch aggregated SO Item quantities using Query Builder
    soi = DocType("Sales Order Item")
    so_item_agg = (
        frappe.qb.from_(soi)
        .select(
            soi.parent,
            Sum(soi.qty).as_("ordered_qty"),
            Sum(soi.picked_qty).as_("picked_qty"),
            Sum(soi.delivered_qty).as_("delivered_qty")
        )
        .where(soi.parent.isin(so_names))
        .groupby(soi.parent)
    ).run(as_dict=True)
    
    # Create lookup map for SO item quantities
    so_item_map = {row.parent: row for row in so_item_agg}
    
    # Fetch Pick List data
    pl_data_map = get_pick_list_data(so_names)
    
    # Fetch Delivery Note data
    dn_data_map = get_delivery_note_data(so_names)
    
    # Fetch Sales Invoice data
    si_data_map = get_sales_invoice_data(so_names)
    
    
    return sales_orders, pl_data_map, dn_data_map, si_data_map, so_item_map

def get_item_level_data(so_names):
    if not so_names: return []
    placeholders = ", ".join(["%s"] * len(so_names))
    query = f"""
        SELECT
            soi.parent AS sales_order,
            soi.item_code,
            soi.item_name,

            
                        
            COALESCE(
                NULLIF(
                    SUBSTRING_INDEX(
                        GROUP_CONCAT(tis.supplier_part_no ORDER BY tis.idx SEPARATOR ', '),
                    ', ', 1),
                ''),
            NULL) AS item_sku,
            GROUP_CONCAT(DISTINCT pli.warehouse SEPARATOR ', ') as pl_warehouse,

            
            
            soi.qty AS ordered_qty,
            COALESCE(soi.picked_qty, 0) AS picked_qty,
            COALESCE(soi.delivered_qty, 0) AS delivered_qty,
            GROUP_CONCAT(DISTINCT CONCAT_WS('::', pl.name, DATE_FORMAT(pl.creation, '%%d-%%m-%%Y'), pli.warehouse, pl.status) SEPARATOR ';;;') AS pl_details,
            GROUP_CONCAT(DISTINCT CONCAT_WS('::', dn.name, DATE_FORMAT(dn.posting_date, '%%d-%%m-%%Y'), dn.status) SEPARATOR ';;;') AS dn_details,
            GROUP_CONCAT(DISTINCT CONCAT_WS('::', si.name, DATE_FORMAT(si.posting_date, '%%d-%%m-%%Y'), si.status) SEPARATOR ';;;') AS si_details
        FROM `tabSales Order Item` soi
        LEFT JOIN `tabItem Supplier` tis ON tis.parent = soi.item_code

        LEFT JOIN `tabSales Invoice Item` sii ON sii.sales_order = soi.parent AND sii.item_code = soi.item_code
        LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
        LEFT JOIN `tabPick List Item` pli ON pli.sales_order = soi.parent AND pli.item_code = soi.item_code
        LEFT JOIN `tabPick List` pl ON pl.name = pli.parent AND pl.docstatus = 1
        LEFT JOIN `tabDelivery Note Item` dni ON dni.against_sales_order = soi.parent AND dni.item_code = soi.item_code
        LEFT JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
        WHERE soi.parent IN ({placeholders})
        GROUP BY soi.parent, soi.item_code, soi.item_name
        ORDER BY soi.parent, soi.idx
    """
    return frappe.db.sql(query, tuple(so_names), as_dict=1)





def build_so_filters(filters):
    """Build filters for Sales Order get_list"""
    so_filters = {"docstatus": ["!=", 2]}
    
    # Handle date range filters
    if filters.get("from_date") and filters.get("to_date"):
        so_filters["transaction_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
    elif filters.get("from_date"):
        so_filters["transaction_date"] = [">=", filters.get("from_date")]
    elif filters.get("to_date"):
        so_filters["transaction_date"] = ["<=", filters.get("to_date")]
    
    if filters.get("customer"):
        so_filters["customer"] = filters.get("customer")
    
    if filters.get("sales_order"):
        so_filters["name"] = filters.get("sales_order")
    
    if filters.get("po_no"):
        so_filters["po_no"] = filters.get("po_no")
    
    if filters.get("so_status"):
        so_filters["status"] = filters.get("so_status")
    
    return so_filters


def get_pick_list_data(so_names):
    """Fetch Pick List data for given SOs"""
    if not so_names:
        return {}
    
    pli = DocType("Pick List Item")
    pl = DocType("Pick List")
    
    valid_statuses = VALID_STATUSES["Pick List"]
    
    pl_data = (
        frappe.qb.from_(pli)
        .left_join(pl).on(pli.parent == pl.name)
        .select(
            pli.sales_order,
            pl.name.as_("pl_name"),
            pl.status.as_("pl_status"),
            pl.creation.as_("pl_creation_date"),
            pli.warehouse
        )
        .where(pli.sales_order.isin(so_names))
        .where(pl.docstatus == 1)
        .where(pl.status.isin(valid_statuses))
        .where(pli.sales_order != "")
        .distinct()
    ).run(as_dict=True)
    
    # Group by SO and aggregate
    pl_map = {}
    for row in pl_data:
        so = row.sales_order
        if so not in pl_map:
            pl_map[so] = {
                "pl_names": [],
                "pl_statuses": [],
                "pl_dates": [],
                "pl_warehouses": [],
                "pl_count": 0
            }
        
        if row.pl_name and row.pl_name not in pl_map[so]["pl_names"]:
            pl_map[so]["pl_names"].append(row.pl_name)
            pl_map[so]["pl_statuses"].append(row.pl_status or "N/A")
            pl_map[so]["pl_dates"].append(row.pl_creation_date.strftime("%Y-%m-%d") if row.pl_creation_date else "")
            pl_map[so]["pl_warehouses"].append(row.warehouse or "")
            pl_map[so]["pl_count"] += 1
    
    for so_name, so_data in pl_map.items():
        # 1. Simple string for export
        so_data["pl_for_export"] = ", ".join(so_data["pl_names"])

        # 2. Rich list of dictionaries for UI
        ui_details = []
        for i in range(so_data['pl_count']):
            name = so_data['pl_names'][i]
            status = so_data['pl_statuses'][i]
            date = so_data['pl_dates'][i]
            warehouse = so_data['pl_warehouses'][i]
            color = STATUS_COLORS.get(status, "#00ff84")

            link_html = f'<a href="/app/pick-list/{name}" target="_blank">{name}</a>'
            status_html = f'<span style="color:{color};">{status}</span>'

            ui_details.append({
                "link_html": link_html,
                "date": date,
                "warehouse": warehouse,
                "status_html": status_html
            })
        so_data["pl_ui_details"] = ui_details


    return pl_map


def get_delivery_note_data(so_names):
    """Fetch Delivery Note data for given SOs"""
    if not so_names:
        return {}
    
    dni = DocType("Delivery Note Item")
    dn = DocType("Delivery Note")
    
    valid_statuses = VALID_STATUSES["Delivery Note"]
    
    dn_data = (
        frappe.qb.from_(dni)
        .left_join(dn).on(dni.parent == dn.name)
        .select(
            dni.against_sales_order,
            dn.name.as_("dn_name"),
            dn.total.as_("dn_total"),
            dn.status.as_("dn_status"),
            dn.posting_date.as_("dn_posting_date")
        )
        .where(dni.against_sales_order.isin(so_names))
        .where(dn.docstatus == 1)
        .where(dn.status.isin(valid_statuses))
        .where(dni.against_sales_order != "")
        .distinct()
    ).run(as_dict=True)
    
    # Group by SO and aggregate
    dn_map = {}
    for row in dn_data:
        so = row.against_sales_order
        if so not in dn_map:
            dn_map[so] = {
                "dn_names": [],
                "dn_statuses": [],
                "dn_dates": [],
                "dn_totals": [],
                "dn_count": 0
            }
        
        if row.dn_name and row.dn_name not in dn_map[so]["dn_names"]:
            dn_map[so]["dn_names"].append(row.dn_name)
            dn_map[so]["dn_statuses"].append(row.dn_status or "N/A")
            dn_map[so]["dn_dates"].append(row.dn_posting_date.strftime("%Y-%m-%d") if row.dn_posting_date else "")
            dn_map[so]["dn_totals"].append(row.dn_total or 0)
            dn_map[so]["dn_count"] += 1
    
    for so_name, so_data in dn_map.items():
        # 1. Simple string for export
        so_data["dn_for_export"] = ", ".join(so_data["dn_names"])
        so_data["dn_amount"] = sum(so_data["dn_totals"])

        # 2. Rich list of dictionaries for UI
        ui_details = []
        for i in range(so_data['dn_count']):
            name = so_data['dn_names'][i]
            status = so_data['dn_statuses'][i]
            date = so_data['dn_dates'][i]
            color = STATUS_COLORS.get(status, "#00ff84")

            link_html = f'<a href="/app/delivery-note/{name}" target="_blank">{name}</a>'
            status_html = f'<span style="color:{color};">{status}</span>'

            ui_details.append({
                "link_html": link_html,
                "date": date,
                "status_html": status_html
            })
        so_data["dn_ui_details"] = ui_details


    return dn_map


def get_sales_invoice_data(so_names):
    """Fetch Sales Invoice data for given SOs"""
    if not so_names:
        return {}
    
    sii = DocType("Sales Invoice Item")
    si = DocType("Sales Invoice")
    
    valid_statuses = VALID_STATUSES["Sales Invoice"]
    
    si_data = (
        frappe.qb.from_(sii)
        .left_join(si).on(sii.parent == si.name)
        .select(
            sii.sales_order,
            si.name.as_("si_name"),
            si.total.as_("si_total"),
            si.status.as_("si_status"),
            si.posting_date.as_("si_posting_date")
        )
        .where(sii.sales_order.isin(so_names))
        .where(si.docstatus == 1)
        .where(si.status.isin(valid_statuses))
        .where(sii.sales_order != "")
        .distinct()
    ).run(as_dict=True)
    
    # Group by SO and aggregate
    si_map = {}
    for row in si_data:
        so = row.sales_order
        if so not in si_map:
            si_map[so] = {
                "si_names": [],
                "si_statuses": [],
                "si_dates": [],
                "si_totals": [],
                "si_count": 0
            }
        
        if row.si_name and row.si_name not in si_map[so]["si_names"]:
            si_map[so]["si_names"].append(row.si_name)
            si_map[so]["si_statuses"].append(row.si_status or "N/A")
            si_map[so]["si_dates"].append(row.si_posting_date.strftime("%Y-%m-%d") if row.si_posting_date else "")
            si_map[so]["si_totals"].append(row.si_total or 0)
            si_map[so]["si_count"] += 1
    
    for so_name, so_data in si_map.items():
        # 1. Simple string for export
        so_data["si_for_export"] = ", ".join(so_data["si_names"])
        so_data["si_amount"] = sum(so_data["si_totals"])

        # 2. Rich list of dictionaries for UI
        ui_details = []
        for i in range(so_data['si_count']):
            name = so_data['si_names'][i]
            status = so_data['si_statuses'][i]
            date = so_data['si_dates'][i]
            color = STATUS_COLORS.get(status, "#00ff84")

            link_html = f'<a href="/app/sales-invoice/{name}" target="_blank">{name}</a>'
            status_html = f'<span style="color:{color}; ">{status}</span>'

            ui_details.append({
                "link_html": link_html,
                "date": date,
                "status_html": status_html
            })
        so_data["si_ui_details"] = ui_details
    
    return si_map



def parse_item_details(details_str, doctype_route, has_warehouse=False):
    """Parses a bundled string from the item-level query."""
    export_list = []
    ui_details_list = []
    if not details_str:
        return export_list, ui_details_list

    for record in details_str.split(';;;'):
        parts = record.split('::')
        
        if has_warehouse and len(parts) == 4:
            name, date, warehouse, status = parts
        elif not has_warehouse and len(parts) == 3:
            name, date, status = parts
            warehouse = None
        else:
            continue

        export_list.append(name)
        color = STATUS_COLORS.get(status, "#00ff84")
        link_html = f'<a href="/app/{doctype_route}/{name}" target="_blank">{name}</a>'
        status_html = f'<span style="color:{color};">{status}</span>'
        
        detail = {
            "link_html": link_html,
            "date": date or "",
            "status_html": status_html
        }
        if warehouse:
            detail["warehouse"] = warehouse
            
        ui_details_list.append(detail)

    return export_list, ui_details_list
