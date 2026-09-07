import frappe
from frappe import _
from frappe.utils import flt 


def get_field_label(doctype, fieldname):
    try:
        meta = frappe.get_meta(doctype)
        df = meta.get_field(fieldname)
        return df.label if df else fieldname 
    except Exception:
        return fieldname






def execute(filters=None):

    columns = get_columns()
    data = []

    # Get list of all submitted pr names
    submitted_pr_names = frappe.get_list(
        "Purchase Receipt", 
        filters={"docstatus": 1}, 
        pluck="name", 
    )

    if not submitted_pr_names:
        return columns,[]
    

# loop through each pr and get the item detail
    pr_header_cache = {}
    pi_header_cache = {}
    for current_pr in submitted_pr_names:
        pr_items = []
        # Getting the pr_items in the 
        try:
            pr_items = frappe.get_all(
                "Purchase Receipt Item",
                fields = [
                    "name as pr_item_id",
                    "parent as purchase_receipt",
                    "item_code",
                    "item_name",
                    "description",
                    "received_qty",
                    "rate",
                    "amount",
                    "warehouse",
                    "purchase_order_item",
                    "purchase_order",
                    "purchase_invoice",
                    "idx",
                    "purchase_invoice_item"
                ],
                filters=[["parent", "=", current_pr]],
                order_by="parent, idx"
            )
        except:
            print.log("Error in getting pr_item {pr_item}")






        for pr_item in pr_items:
            parent_pr_name = pr_item.purchase_receipt
            pr_details = pr_header_cache.get(parent_pr_name)
            if not pr_details:
                pr_details = frappe.get_value(
                    "Purchase Receipt",
                    parent_pr_name,
                    [
                        "posting_date as pr_posting_date",
                        "supplier"
                    ],
                    as_dict=True
                )
            pr_item.pr_posting_date = pr_details.get("pr_posting_date")

            pr_item.supplier = pr_details.get("supplier")
            pr_header_cache[parent_pr_name] = pr_details or {}


            
            # Get the pi details
            linked_pi_name = pr_item.purchase_invoice
            linked_pi_item_name = pr_item.purchase_invoice_item
            pi_item_matches = []
            pi_header_info = None

            if linked_pi_name:
                pi_header_info = pi_header_cache.get(linked_pi_name)
                if not pi_header_info:
                    pi_header_info = frappe.get_value(
                        "Purchase Invoice",
                        linked_pi_name,
                        [
                            "name",
                            "bill_no",
                            "bill_date",
                            "posting_date as pi_posting_date"
                        ],
                        as_dict = True
                    )
                pi_header_cache[linked_pi_name] = pi_header_info or {}



            print(linked_pi_item_name)

            if linked_pi_item_name:
                print(linked_pi_item_name)
                pi_item_details = frappe.get_value(
                    "Purchase Invoice Item",
                    linked_pi_item_name, # Use the direct link name
                    [
                        "name AS pi_item_id",
                        "parent AS purchase_invoice", 
                        "qty", 
                        "rate", 
                        "amount"
                    ],
                    as_dict=True
                )
                print(pi_item_details)
            else:
                pi_item_details = {}


            row = prepare_row(pr_item, pi_item_details, pi_header_info or {})
            data.append(row)


    return columns,data




def prepare_row(pr_item,pi_item,pi_header_info):

    row = {
        "supplier": pr_item.supplier, "item_code": pr_item.item_code,
        "item_name": pr_item.item_name, "description": pr_item.description,
        "purchase_receipt": pr_item.purchase_receipt,
        "pr_posting_date": pr_item.pr_posting_date, "pr_item_id": pr_item.pr_item_id,
        "pr_qty": pr_item.received_qty, "pr_rate": pr_item.rate, "pr_amount": pr_item.amount,
        "warehouse": pr_item.warehouse, "purchase_invoice": None, "pi_posting_date": None,
        "pi_item_id": None, "pi_qty": None, "pi_rate": None, "pi_amount": None,
        "supplier_bill_no": None, "supplier_bill_date": None, "qty_difference": None,
        "amount_difference": None
    }
    if pi_header_info:
        row["purchase_invoice"] = pi_header_info.get("name")
        row["pi_posting_date"] = pi_header_info.get("pi_posting_date")
        row["supplier_bill_no"] = pi_header_info.get("bill_no")
        row["supplier_bill_date"] = pi_header_info.get("bill_date")
    if pi_item:
        row["pi_item_id"] = pi_item.pi_item_id
        row["pi_qty"] = pi_item.qty
        row["pi_rate"] = pi_item.rate
        row["pi_amount"] = pi_item.amount
        row["qty_difference"] = flt(pi_item.qty) - flt(pr_item.received_qty)
        row["amount_difference"] = flt(pi_item.amount) - flt(pr_item.amount)
    return row




def get_columns():
        return [
        {"fieldname": "purchase_receipt",   "label": _("Purchase Receipt"), "fieldtype": "Link", "options": "Purchase Receipt", "width": 230}, 
        {"fieldname": "purchase_invoice",   "label": _("Purchase Invoice"), "fieldtype": "Link", "options": "Purchase Invoice", "width": 230}, 
        {"fieldname": "item_code",          "label": _(get_field_label("Purchase Receipt Item", "item_code")), "fieldtype": "Link", "options": "Item", "width": 120},
        {"fieldname": "item_name",          "label": _(get_field_label("Purchase Receipt Item", "item_name")), "fieldtype": "Data", "width": 150},
        # {"fieldname": "description",        "label": _(get_field_label("Purchase Receipt Item", "description")), "fieldtype": "Data", "width": 180},
        {"fieldname": "supplier",           "label": _(get_field_label("Purchase Receipt", "supplier")), "fieldtype": "Link", "options": "Supplier", "width": 140},
        {"fieldname": "supplier_bill_no",   "label": _(get_field_label("Purchase Invoice", "bill_no")), "fieldtype": "Data", "width": 160}, 
        {"fieldname": "supplier_bill_date", "label": _(get_field_label("Purchase Invoice", "bill_date")), "fieldtype": "Date", "width": 180}, 

        {"fieldname": "pr_qty",             "label": _("PR Qty"), "fieldtype": "Float", "width": 90, "precision": 3}, 
        {"fieldname": "pi_qty",             "label": _("PI Qty"), "fieldtype": "Float", "width": 90, "precision": 3},
        {"fieldname": "qty_difference", "label": _("Qty Diff (PI-PR)"), "fieldtype": "Float", "width": 130, "precision": 3},
        {"fieldname": "pr_amount",          "label": _("PR Amount"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "pi_amount",          "label": _("PI Amount"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "amount_difference", "label": _("Amt Diff (PI-PR)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "pr_posting_date",    "label": _("PR Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "pi_posting_date",    "label": _("PI Date"), "fieldtype": "Date", "width": 100},
        # {"fieldname": "pr_item_id",         "label": _("PR Item ID"), "fieldtype": "Data", "width": 130},
        # {"fieldname": "pi_item_id",         "label": _("PI Item ID"), "fieldtype": "Data", "width": 130},
        {"fieldname": "pr_rate",            "label": _("PR Rate"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "pi_rate",            "label": _("PR Rate"), "fieldtype": "Currency", "width": 100},

        {"fieldname": "warehouse",          "label": _(get_field_label("Purchase Receipt Item", "warehouse")), "fieldtype": "Link", "options": "Warehouse", "width": 170},

    ]