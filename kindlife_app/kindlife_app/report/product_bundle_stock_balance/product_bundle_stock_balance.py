# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

"""
Product Bundle Stock Balance Report

Calculates the virtual sellable stock for every Product Bundle by applying
the same min-floor logic used by the CS Cart inventory sync:

    bundle_qty = floor( min( component_stock / component_qty_in_bundle ) )

Computed independently for:
  - Good Qty  (non-rejected warehouses)
  - Bad Qty   (rejected warehouses)
  - Open Order Qty (allocated in active Pick Lists)

The "bottleneck component" — the component that limits the bundle qty — is
also surfaced so teams can quickly identify what to restock.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate
from erpnext.stock.utils import get_stock_balance
from erpnext.stock.doctype.warehouse.warehouse import get_child_warehouses


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	return columns, data


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def get_columns():
	return [
		{
			"label": _("Product Bundle"),
			"fieldname": "product_bundle",
			"fieldtype": "Link",
			"options": "Product Bundle",
			"width": 220,
		},
		{
			"label": _("Bundle Item"),
			"fieldname": "bundle_item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 200,
		},
		{
			"label": _("Bundle Item Name"),
			"fieldname": "bundle_item_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("CS Cart Product Code"),
			"fieldname": "product_code",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Type"),
			"fieldname": "item_type",
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"label": _("No. of Components"),
			"fieldname": "num_components",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("Good Qty"),
			"fieldname": "good_qty",
			"fieldtype": "Float",
			"width": 110,
			"precision": 0,
		},
		{
			"label": _("Bad Qty"),
			"fieldname": "bad_qty",
			"fieldtype": "Float",
			"width": 100,
			"precision": 0,
		},
		{
			"label": _("Open Order Qty"),
			"fieldname": "open_order_qty",
			"fieldtype": "Float",
			"width": 130,
			"precision": 0,
		},
		{
			"label": _("Net Available Qty"),
			"fieldname": "net_available_qty",
			"fieldtype": "Float",
			"width": 140,
			"precision": 0,
		},
		{
			"label": _("Bottleneck Component"),
			"fieldname": "bottleneck_component",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Bottleneck Stock"),
			"fieldname": "bottleneck_stock",
			"fieldtype": "Float",
			"width": 140,
			"precision": 2,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 200,
		},
	]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def get_data(filters):
	warehouses = resolve_warehouses(filters)
	if not warehouses:
		frappe.throw(_("No warehouse found. Either select a warehouse in the filter or configure a main warehouse (custom_main_warehouse = 1)."))

	# Merge good / rejected leaf warehouses across ALL main warehouses once
	all_good, all_rejected = [], []
	for wh in warehouses:
		g, r = classify_warehouses(wh)
		all_good.extend(g)
		all_rejected.extend(r)
	# Deduplicate (a child may theoretically appear under multiple group parents)
	all_good     = list(set(all_good))
	all_rejected = list(set(all_rejected))

	warehouse_label = ", ".join(warehouses)

	# Fetch all Product Bundles (optionally filter by specific bundle)
	bundle_filters = {}
	if filters.get("product_bundle"):
		bundle_filters["name"] = filters["product_bundle"]

	bundles = frappe.db.get_all(
		"Product Bundle",
		filters=bundle_filters,
		fields=["name", "new_item_code", "description"],
		order_by="new_item_code"
	)

	if not bundles:
		return []

	# Pre-fetch all parent item details in one shot
	bundle_item_codes = [b.new_item_code for b in bundles if b.new_item_code]
	item_details_map = {}
	if bundle_item_codes:
		items = frappe.db.get_all(
			"Item",
			filters={"name": ["in", bundle_item_codes]},
			fields=["name", "item_name", "custom_type"]
		)
		# Get supplier_part_no for each item (first supplier row)
		for item in items:
			supplier_part_no = frappe.db.get_value(
				"Item Supplier",
				{"parent": item.name},
				"supplier_part_no"
			)
			item_details_map[item.name] = {
				"item_name": item.item_name,
				"custom_type": item.custom_type,
				"product_code": supplier_part_no or ""
			}

	# Pre-compute warehouse sets (good vs rejected) - already done above

	data = []
	for bundle in bundles:
		if not bundle.new_item_code:
			continue

		item_detail = item_details_map.get(bundle.new_item_code, {})
		item_type = item_detail.get("custom_type", "")

		# Apply bundle type filter
		bundle_type_filter = filters.get("bundle_type", "All")
		if bundle_type_filter and bundle_type_filter != "All":
			if item_type != bundle_type_filter:
				continue

		# Fetch components
		components = frappe.db.get_all(
			"Product Bundle Item",
			filters={"parent": bundle.name},
			fields=["item_code", "qty", "description"],
			order_by="idx"
		)

		if not components:
			continue

		result = calculate_bundle_stock(
			components, warehouses[0], all_good, all_rejected
		)

		good_qty = result["good_qty"]
		bad_qty = result["bad_qty"]
		open_order_qty = result["open_order_qty"]
		bottleneck_component = result["bottleneck_component"]
		bottleneck_stock = result["bottleneck_stock"]

		# Net available = Good - Open Orders (cannot go below 0)
		net_available_qty = max(0.0, good_qty - open_order_qty)

		# Apply zero-stock filter
		if not filters.get("show_zero_stock") and good_qty == 0 and net_available_qty == 0:
			continue

		data.append({
			"product_bundle": bundle.name,
			"bundle_item_code": bundle.new_item_code,
			"bundle_item_name": item_detail.get("item_name", ""),
			"product_code": item_detail.get("product_code", ""),
			"item_type": item_type,
			"num_components": len(components),
			"good_qty": good_qty,
			"bad_qty": bad_qty,
			"open_order_qty": open_order_qty,
			"net_available_qty": net_available_qty,
			"bottleneck_component": bottleneck_component,
			"bottleneck_stock": bottleneck_stock,
			"warehouse": warehouse_label,
		})

	return data


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def calculate_bundle_stock(components, warehouse, good_warehouses, rejected_warehouses):
	"""
	For each component, compute good_qty and open_order_qty by looking up
	stock balance across classified warehouse lists.

	Returns a dict with:
	  good_qty, bad_qty, open_order_qty,
	  bottleneck_component, bottleneck_stock
	"""
	min_good = float("inf")
	min_bad = float("inf")
	min_open = float("inf")
	bottleneck_component = ""
	bottleneck_stock = 0.0

	for row in components:
		comp_code = row.item_code
		comp_qty_per_bundle = flt(row.qty) or 1

		# --- Good Qty ---
		print("comp_code", comp_code)
		print("good_warehouses", good_warehouses)
		comp_good = sum(
			flt(get_stock_balance(comp_code, wh, posting_date=nowdate()))
			for wh in good_warehouses
		)

		# --- Bad Qty ---
		comp_bad = sum(
			flt(get_stock_balance(comp_code, wh, posting_date=nowdate()))
			for wh in rejected_warehouses
		)

		# --- Open Order Qty (active pick lists) ---
		comp_open = get_pick_list_reserved_qty(comp_code, warehouse)

		# Floor division — only whole bundles can be made
		possible_good = comp_good // comp_qty_per_bundle
		possible_bad  = comp_bad  // comp_qty_per_bundle
		possible_open = comp_open // comp_qty_per_bundle

		if possible_good < min_good:
			min_good = possible_good
			bottleneck_component = f"{comp_code} ({comp_good} in stock, {comp_qty_per_bundle} needed/bundle)"
			bottleneck_stock = comp_good

		min_bad  = min(min_bad,  possible_bad)
		min_open = min(min_open, possible_open)

	return {
		"good_qty":             max(0.0, min_good if min_good != float("inf") else 0.0),
		"bad_qty":              max(0.0, min_bad  if min_bad  != float("inf") else 0.0),
		"open_order_qty":       max(0.0, min_open if min_open != float("inf") else 0.0),
		"bottleneck_component": bottleneck_component,
		"bottleneck_stock":     bottleneck_stock,
	}


def get_pick_list_reserved_qty(item_code, warehouse):
	"""
	Return qty of item_code allocated in active (non-Completed, non-Cancelled)
	Pick Lists within the given warehouse (or any of its children if it's a group).
	"""
	try:
		warehouses = [warehouse]
		is_group = frappe.db.get_value("Warehouse", warehouse, "is_group")
		if is_group:
			warehouses = get_child_warehouses(warehouse)

		if not warehouses:
			return 0.0

		result = frappe.db.sql("""
			SELECT
				SUM(
					CASE
						WHEN (pli.picked_qty > 0 AND pli.docstatus = 1)
						THEN pli.picked_qty - IFNULL(pli.delivered_qty, 0)
						ELSE pli.stock_qty
					END
				) AS reserved_qty
			FROM `tabPick List Item` pli
			INNER JOIN `tabPick List` pl ON pl.name = pli.parent
			WHERE pli.item_code = %(item_code)s
				AND pli.warehouse IN %(warehouses)s
				AND pl.status NOT IN ('Completed', 'Cancelled')
				AND pli.docstatus != 2
				AND (pli.picked_qty > 0 OR pli.stock_qty > 0)
		""", {"item_code": item_code, "warehouses": warehouses}, as_dict=True)

		return flt(result[0].reserved_qty) if result else 0.0

	except Exception:
		return 0.0


# ---------------------------------------------------------------------------
# Warehouse helpers
# ---------------------------------------------------------------------------

def resolve_warehouses(filters):
	"""
	Return the list of warehouses to use for stock lookup.
	Priority: single filter value → all main warehouses (custom_main_warehouse = 1).
	"""
	if filters.get("warehouse"):
		return [filters["warehouse"]]

	main_warehouses = frappe.db.get_all(
		"Warehouse",
		filters={"custom_main_warehouse": 1, "is_group": 1},
		pluck="name"
	)
	return main_warehouses or []


def classify_warehouses(warehouse):
	"""
	Return (good_leaf_warehouses, rejected_leaf_warehouses) under ``warehouse``.
	If warehouse is a leaf, classifies itself.
	"""
	is_group = frappe.db.get_value("Warehouse", warehouse, "is_group")

	if not is_group:
		is_rejected = frappe.db.get_value("Warehouse", warehouse, "is_rejected_warehouse")
		is_qc = frappe.db.get_value("Warehouse", warehouse, "custom_is_qc_warehouse")
		if is_rejected:
			return [], [warehouse]
		if is_qc:
			return [], []  # QC stock is neither good nor bad
		return [warehouse], []

	children = get_child_warehouses(warehouse)

	rejected = frappe.db.get_all(
		"Warehouse",
		filters={"name": ["in", children], "is_rejected_warehouse": 1},
		pluck="name"
	) or []
	rejected_set = set(rejected)

	qc_warehouses = frappe.db.get_all(
		"Warehouse",
		filters={"name": ["in", children], "custom_is_qc_warehouse": 1},
		pluck="name"
	) or []
	qc_set = set(qc_warehouses)

	good = [
		wh for wh in children
		if wh != warehouse
		and wh not in rejected_set
		and wh not in qc_set
		and not frappe.db.get_value("Warehouse", wh, "is_group")
	]

	rejected_leaves = [
		wh for wh in rejected
		if not frappe.db.get_value("Warehouse", wh, "is_group")
	]

	return good, rejected_leaves
