# shipment_utils.py
# Three-function chain for propagating shipment fields
# (custom_shipment_document, custom_shipment_id)
# from Sales Order Items to Pick List, Delivery Note, and Purchase Order Items.
#
# Function 1 (get_item_fields_mapping):    SO → {item_code: {field: value}}
# Function 2 (set_fields_on_child_table):  doc + mapping → sets fields on rows
# Function 3 (sync_shipment_for_doc/so):   Orchestrators called from hooks & API

import frappe
from frappe import _

# Fields to propagate from Sales Order Item to child docs
PROPAGATED_FIELDS = ["custom_shipment_document", "custom_shipment_id", "custom_awb_number"]

# Fields that should ALWAYS overwrite (Last Call Wins)
OVERWRITE_FIELDS = ["custom_awb_number"]


# ─────────────────────────────────────────────────────────────────────────────
# Function 1: Data Fetcher
# ─────────────────────────────────────────────────────────────────────────────

def get_item_fields_mapping(sales_order_id, item_codes=None):
    """
    Fetch propagated field values from Sales Order Item rows.

    Returns:
        dict - { item_code: { field_name: value, ... } }
        Only includes items where at least one field is non-empty.
    """
    if not sales_order_id:
        return {}

    filters = {"parent": sales_order_id}

    if item_codes:
        if isinstance(item_codes, str):
            item_codes = [item_codes]
        filters["item_code"] = ["in", item_codes]

    rows = frappe.db.get_all(
        "Sales Order Item",
        filters=filters,
        fields=["item_code"] + PROPAGATED_FIELDS,
    )

    mapping = {}
    for r in rows:
        # Include a field if it has a value, OR if it is an OVERWRITE_FIELDS (to allow clearing)
        vals = {f: r.get(f) for f in PROPAGATED_FIELDS if r.get(f) or f in OVERWRITE_FIELDS}
        if vals:
            mapping[r.item_code] = vals
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# Function 2: Child Table Setter
# ─────────────────────────────────────────────────────────────────────────────

def set_fields_on_child_table(doc, so_mapping, so_link_field, child_table="items"):
    """
    Iterate over the child table and set propagated fields from the mapping.
    Only updates rows whose SO link matches a key in the mapping,
    and only sets a field if it is currently empty on the target row.

    Args:
        doc: Frappe document (Pick List, Delivery Note, or Purchase Order)
        so_mapping: { so_name: { item_code: { field: value } } }
        so_link_field: field on child row holding the SO name
        child_table: child table attribute name
    """
    if not so_mapping:
        return

    for row in (doc.get(child_table) or []):
        so_name = getattr(row, so_link_field, None)
        if not so_name or not row.item_code:
            continue

        item_mapping = so_mapping.get(so_name)
        if not item_mapping:
            continue

        field_vals = item_mapping.get(row.item_code)
        if not field_vals:
            continue

        for field, value in field_vals.items():
            if field in OVERWRITE_FIELDS:
                setattr(row, field, value)
            elif value and not getattr(row, field, None):
                setattr(row, field, value)



# ─────────────────────────────────────────────────────────────────────────────
# Function 3: Orchestrators
# ─────────────────────────────────────────────────────────────────────────────

def sync_shipment_docs_for_doc(doc, so_link_field, child_table="items"):
    """
    Scenario 1 entry-point - called from validate / before_save hooks.

    Groups child rows by Sales Order, fetches the field mapping for each SO,
    then sets the fields on every matching child row.
    """
    # Collect unique (SO -> item_codes) groups
    so_items = {}
    for row in (doc.get(child_table) or []):
        so_name = getattr(row, so_link_field, None)
        if so_name and row.item_code:
            so_items.setdefault(so_name, set()).add(row.item_code)

    if not so_items:
        return

    # Build nested mapping: { so_name: { item_code: {field: val} } }
    so_mapping = {}
    for so_name, codes in so_items.items():
        item_map = get_item_fields_mapping(so_name, list(codes))
        if item_map:
            so_mapping[so_name] = item_map

    # Apply
    set_fields_on_child_table(doc, so_mapping, so_link_field, child_table)


def sync_shipment_docs_for_so(sales_order_id):
    """
    Scenario 2 entry-point - called after shipment data is saved via API.

    Finds all existing Pick Lists, Delivery Notes, and Purchase Orders
    linked to this Sales Order and updates their child rows with both
    custom_shipment_document and custom_shipment_id.
    Uses raw SQL so submitted docs are updated too.
    """
    if not sales_order_id:
        return

    # Get the mapping for ALL items in this SO
    mapping = get_item_fields_mapping(sales_order_id)
    if not mapping:
        return

    # 1. Row-level updates: Delivery Note Item, Purchase Order Item
    row_tables = [
        ("Delivery Note Item", "tabDelivery Note Item", "against_sales_order"),
        ("Purchase Order Item", "tabPurchase Order Item", "sales_order"),
    ]

    for item_code, field_vals in mapping.items():
        for dt, table, so_field in row_tables:
            for field, value in field_vals.items():

                filters = {so_field: sales_order_id, "item_code": item_code}
                if field not in OVERWRITE_FIELDS:
                    filters[field] = ["in", [None, ""]]

                frappe.db.set_value(dt, filters, field, value, update_modified=False)

    for item_code, field_vals in mapping.items():
        for field in ["custom_shipment_id", "custom_shipment_document"]:
            value = field_vals.get(field)
            if not value:
                continue

            filters = {
                "sales_order": sales_order_id,
                "item_code": item_code,
                "docstatus": ["<", 2],
            }

            # For non-overwrite fields, only update if currently empty
            if field not in OVERWRITE_FIELDS:
                # Fetch PL Items and update only those with empty fields
                pl_items = frappe.get_all("Pick List Item", filters=filters, fields=["name", field])
                for pl_item in pl_items:
                    if not pl_item.get(field):  # Only update if empty
                        frappe.db.set_value("Pick List Item", pl_item["name"], field, value, update_modified=False)
            else:
                # For overwrite fields, update all rows
                frappe.db.set_value("Pick List Item", filters, field, value, update_modified=False)
