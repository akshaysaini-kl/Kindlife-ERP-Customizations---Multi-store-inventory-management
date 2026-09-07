import copy
import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import floor, flt

from erpnext.stock.doctype.putaway_rule.putaway_rule import (
    get_ordered_putaway_rules,
    add_row,
    show_unassigned_items_message,
    _items_changed,
)
from frappe.utils.nestedset import get_descendants_of


def aggregate_items_by_warehouse_batch(items):
    """
    Aggregates items with the same item_code, s_warehouse, and batch_no into single rows.
    Merges quantities and concatenates serial numbers.
    """
    aggregated_items_map = {}

    for item in items:
        if isinstance(item, dict):
            item = frappe._dict(item)

        unique_item_key = (item.item_code, item.get("s_warehouse"), item.get("batch_no"))

        if unique_item_key not in aggregated_items_map:
            aggregated_items_map[unique_item_key] = copy.deepcopy(item)
            aggregated_items_map[unique_item_key].qty = flt(item.qty)
            aggregated_items_map[unique_item_key].transfer_qty = flt(item.transfer_qty)
        else:
            aggregated_items_map[unique_item_key].qty += flt(item.qty)
            aggregated_items_map[unique_item_key].transfer_qty += flt(item.transfer_qty)

            if item.get("serial_no"):
                existing_serials = aggregated_items_map[unique_item_key].get("serial_no") or ""
                new_serials = item.get("serial_no")

                if existing_serials and new_serials:
                    aggregated_items_map[unique_item_key].serial_no = existing_serials + "\n" + new_serials
                elif new_serials:
                    aggregated_items_map[unique_item_key].serial_no = new_serials

    return list(aggregated_items_map.values())



@frappe.whitelist()
def apply_putaway_rule(doctype, items, company, sync=None, purpose=None):
    """Applies Putaway Rule on line items.

    items: List of Purchase Receipt/Stock Entry Items
    company: Company in the Purchase Receipt/Stock Entry
    doctype: Doctype to apply rule on
    purpose: Purpose of Stock Entry
    sync (optional): Sync with client side only for client side calls
    """
    if isinstance(items, str):
        items = json.loads(items)

    # Aggregate items with same warehouse and batch
    if doctype == "Stock Entry":
        items = aggregate_items_by_warehouse_batch(items)


    parent_group_name = None
    source_se_warehouse = items[0].get("s_warehouse")
    parent_group_name = frappe.db.get_value("Warehouse", source_se_warehouse, "parent_warehouse")
    descendants = get_descendants_of("Warehouse", parent_group_name, ignore_permissions=True)

    items_not_accomodated, updated_table = [], []
    item_wise_rules = defaultdict(list)

    for item in items:
        if isinstance(item, dict):
            item = frappe._dict(item)

        source_warehouse = item.get("s_warehouse")
        item.conversion_factor = flt(item.conversion_factor) or 1.0
        pending_qty, item_code = flt(item.qty), item.item_code
        pending_stock_qty = flt(item.transfer_qty) if doctype == "Stock Entry" else flt(item.stock_qty)
        uom_must_be_whole_number = frappe.db.get_value("UOM", item.uom, "must_be_whole_number")

        original_serial_nos = item.get("serial_no")
        serial_nos_list = []
        if original_serial_nos:
            serial_nos_list = [s.strip() for s in original_serial_nos.split("\n") if s.strip()]

        if not pending_qty or not item_code:
            updated_table = add_row(item, pending_qty, source_warehouse or item.warehouse, updated_table, None, serial_nos=serial_nos_list)
            continue

        at_capacity, rules = get_ordered_putaway_rules(item_code, company, source_warehouse=source_warehouse)
        if descendants and rules:
            rules = [r for r in rules if r.warehouse in descendants]

        if not rules:
            warehouse = source_warehouse or item.get("warehouse")
            if at_capacity:
                items_not_accomodated.append([item_code, pending_qty])
                updated_table = add_row(item, pending_qty, "", updated_table, None, serial_nos=serial_nos_list)
            else:
                updated_table = add_row(item, pending_qty, warehouse, updated_table, None, serial_nos=serial_nos_list)
            continue

        key = item_code
        if doctype == "Stock Entry" and purpose == "Material Transfer" and source_warehouse:
            key = (item_code, source_warehouse)

        if not item_wise_rules[key]:
            item_wise_rules[key] = rules

        for rule in item_wise_rules[key]:
            if pending_stock_qty > 0 and rule.free_space:
                stock_qty_to_allocate = (
                    flt(rule.free_space) if pending_stock_qty >= flt(rule.free_space) else pending_stock_qty
                )
                qty_to_allocate = stock_qty_to_allocate / item.conversion_factor

                if uom_must_be_whole_number:
                    qty_to_allocate = floor(qty_to_allocate)
                    stock_qty_to_allocate = qty_to_allocate * item.conversion_factor

                if not qty_to_allocate:
                    break

                updated_table = add_row(item, qty_to_allocate, rule.warehouse, updated_table, rule.name, serial_nos=serial_nos_list)

                pending_stock_qty -= stock_qty_to_allocate
                pending_qty -= qty_to_allocate
                rule["free_space"] -= stock_qty_to_allocate

                if not pending_stock_qty > 0:
                    break

        if pending_stock_qty > 0:
            items_not_accomodated.append([item.item_code, pending_qty])
            updated_table = add_row(item, pending_qty, "", updated_table, None, serial_nos=serial_nos_list)

    if items_not_accomodated:
        show_unassigned_items_message(items_not_accomodated)

    if updated_table and _items_changed(items, updated_table, doctype):
        items[:] = updated_table
        frappe.msgprint(_("Applied putaway rules."), alert=True)

    if sync and json.loads(sync):
        return items
