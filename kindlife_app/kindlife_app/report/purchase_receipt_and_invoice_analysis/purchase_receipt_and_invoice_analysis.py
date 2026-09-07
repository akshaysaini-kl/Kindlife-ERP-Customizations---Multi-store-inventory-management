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


    # --- Get PR data 
    pr_headers = frappe.get_all(
        "Purchase Receipt",
        filters={"docstatus": 1},
        fields=["name", "supplier", "posting_date"], 
        as_list=False 
    )
    # Create a dictionary 
    pr_header_map = {pr.pop("name"): pr for pr in pr_headers}
    submitted_pr_names = list(pr_header_map.keys()) 

    # Store values once found
    pi_header_cache = {}

    # 2. Loop through each PR
    for pr_name in submitted_pr_names:

        pr_header_data = pr_header_map.get(pr_name)

        # Make a row
        row_data = {
            "supplier": pr_header_data.get("supplier"),
            "purchase_receipt": pr_name,
            "pr_posting_date": pr_header_data.get("posting_date"),
            "pr_qty_total": 0.0,
            "pr_amount_total": 0.0,
            "purchase_invoice": None, 
            "pi_posting_date": None,
            "pi_qty_total": 0.0,
            "pi_amount_total": 0.0,
        }

        # 3. Info of child table
        pr_items = frappe.get_all(
            "Purchase Receipt Item",
            fields=[
                "name as pr_item_id",
                "received_qty",
                "amount",
                "purchase_invoice", 
                "purchase_invoice_item",
                "item_code", 
                "item_name",
                "description",
                "warehouse"
            ],
            filters={"parent": pr_name},
        )

        # 4. Process each PR item
        for pr_item in pr_items:
            row_data["pr_qty_total"] += flt(pr_item.received_qty)
            row_data["pr_amount_total"] += flt(pr_item.amount)

            # Getting PI detail
            linked_pi_name = pr_item.purchase_invoice
            linked_pi_item_name = pr_item.purchase_invoice_item

            if linked_pi_name and linked_pi_item_name:
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
                        as_dict=True
                    )
                    if pi_header_info:
                        pi_header_cache[linked_pi_name] = pi_header_info
                    else:
                         pi_header_cache[linked_pi_name] = {}


                # Setting pi item detail
                if not row_data.get("purchase_invoice"):
                    row_data["purchase_invoice"] = linked_pi_name
                    row_data["pi_posting_date"] = pi_header_info.get("pi_posting_date")
                    row_data["supplier_bill_no"] = pi_header_info.get("bill_no") 
                    row_data["supplier_bill_date"] = pi_header_info.get("bill_date") 

                # Get the specific PI item details
                pi_item_match = frappe.get_value(
                    "Purchase Invoice Item",
                    linked_pi_item_name,
                    [
                        "qty", 
                        "amount", 
                        "name as pi_item_id"
                    ],
                    as_dict=True
                )

                if pi_item_match:
                    row_data["pi_qty_total"] += flt(pi_item_match.qty)
                    row_data["pi_amount_total"] += flt(pi_item_match.amount)
              

        # Add Difference
        row_data["qty_difference"] = row_data["pr_qty_total"] - row_data["pi_qty_total"]
        row_data["amount_difference"] = row_data["pr_amount_total"] - row_data["pi_amount_total"]

        # Add data to list
        data.append(row_data)

    return columns, data


def get_columns():
    return [
        {"fieldname": "supplier", "label": _(get_field_label("Purchase Receipt", "supplier")), "fieldtype": "Link", "options": "Supplier", "width": 170},
        # {"fieldname": "supplier_bill_no", "label": _(get_field_label("Purchase Invoice", "bill_no")), "fieldtype": "Data", "width": 120},
        # {"fieldname": "supplier_bill_date", "label": _(get_field_label("Purchase Invoice", "bill_date")), "fieldtype": "Date", "width": 110},
        {"fieldname": "purchase_receipt", "label": _("Purchase Receipt"), "fieldtype": "Link", "options": "Purchase Receipt", "width": 290},
        # {"fieldname": "purchase_invoice", "label": _("Purchase Invoice"), "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
        {"fieldname": "pr_posting_date", "label": _("PR Date"), "fieldtype": "Date", "width": 160}, 
        # {"fieldname": "pi_posting_date", "label": _("PI Date"), "fieldtype": "Date", "width": 100},
        # {"fieldname": "pr_item_id", "label": _("PR Item ID"), "fieldtype": "Data", "width": 130}, 
        # {"fieldname": "pi_item_id", "label": _("PI Item ID"), "fieldtype": "Data", "width": 130}, 
        {"fieldname": "pr_qty_total", "label": _("PR Qty"), "fieldtype": "Float", "width": 145, "precision": 3}, 
        {"fieldname": "pi_qty_total", "label": _("PI Qty"), "fieldtype": "Float", "width": 145, "precision": 3}, 
        {"fieldname": "qty_difference", "label": _("Qty Diff (PR-PI)"), "fieldtype": "Float", "width": 200, "precision": 3}, 
        # {"fieldname": "pr_rate", "label": _("PR Rate"), "fieldtype": "Currency", "width": 100}, 
        # {"fieldname": "pi_rate", "label": _("PI Rate"), "fieldtype": "Currency", "width": 100}, 
        {"fieldname": "pr_amount_total", "label": _("PR Amount"), "fieldtype": "Currency", "width": 155},
        {"fieldname": "pi_amount_total", "label": _("PI Amount"), "fieldtype": "Currency", "width": 155},
        {"fieldname": "amount_difference", "label": _("Amt Diff (PR-PI)"), "fieldtype": "Currency", "width": 175}, 
    ]