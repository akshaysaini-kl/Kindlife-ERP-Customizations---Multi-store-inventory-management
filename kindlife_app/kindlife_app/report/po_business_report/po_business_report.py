# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from collections import OrderedDict


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	# Total width = 1740
	return [
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 400,
		},
		{
			"label": _("No of PO's"),
			"fieldname": "total_pos",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": _("Total MRP value"),
			"fieldname": "total_mrp",
			"fieldtype": "Currency",
			"width": 200,
			"precision": 2
		},
		{
			"label": _("Total PO Value"),
			"fieldname": "total_po_amount",
			"fieldtype": "Currency",
			"width": 210,
			"precision": 2
		},
		{
			"label": _("Discount %"),
			"fieldname": "discount_stats",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("PI value"),
			"fieldname": "total_pi_amount",
			"fieldtype": "Currency",
			"width": 110,
			"precision": 2
		},
		{
			"label": _("PI% of PO value"),
			"fieldname": "pi_percentage",
			"fieldtype": "Percent",
			"width": 150,
			"precision": 2
		},
		{
			"label": _("Goods Received (Remaining)"),
			"fieldname": "received_stats",
			"fieldtype": "Data",
			"width": 200,
		},
	]


def get_data(filters):
	conditions = get_conditions(filters)

	# Get details of all the po that fit the filters
	purchase_orders = frappe.db.sql(
		f"""
		SELECT
			po.name,
			po.supplier,
			po.supplier_name,
			po.conversion_rate,
			(SELECT SUM(poi.qty * poi.discount_amount) FROM `tabPurchase Order Item` poi WHERE poi.parent = po.name) as row_discount_currency,
			(SELECT SUM(poi.qty * poi.custom_list_price) FROM `tabPurchase Order Item` poi WHERE poi.parent = po.name) as po_mrp_currency,
			po.base_discount_amount as header_discount,
			po.base_total,
			po.base_net_total,
			po.base_grand_total,
			po.per_billed,
			po.per_received,
			po.total_qty,
			po.currency
		FROM
			`tabPurchase Order` po
		WHERE
			po.docstatus = 1
			{conditions}
		ORDER BY
			po.supplier_name
		""",
		filters,
		as_dict=1,
	)

	if not purchase_orders:
		return []

	# Get PI counts per PO (submitted PIs only)
	po_names = [po.name for po in purchase_orders]
	pi_data = frappe.db.sql(
		"""
		SELECT
			pii.purchase_order,
			COUNT(DISTINCT pii.parent) as pi_count
		FROM
			`tabPurchase Invoice Item` pii
		INNER JOIN
			`tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE
			pi.docstatus = 1
			AND pii.purchase_order IN %(po_names)s
		GROUP BY
			pii.purchase_order
		""",
		{"po_names": po_names},
		as_dict=1,
	)

	pi_count_map = {d.purchase_order: d.pi_count for d in pi_data}

	# Group by supplier
	supplier_groups = OrderedDict()
	for po in purchase_orders:
		supplier = po.supplier
		if supplier not in supplier_groups:
			supplier_groups[supplier] = {
				"supplier_name": po.supplier_name or po.supplier,
				"orders": [],
			}
		supplier_groups[supplier]["orders"].append(po)

	# Build flat data — one row per supplier
	data = []
	company_currency = frappe.get_cached_value(
		"Company", frappe.db.get_default("company"), "default_currency"
	)

	for supplier, group in supplier_groups.items():
		total_po_count = len(group["orders"])
		total_discount = 0
		total_gross = 0
		total_po_value = 0
		total_mrp = 0
		total_billed = 0
		total_received_qty = 0
		total_remaining_qty = 0
		total_pi_count = 0

		for po in group["orders"]:
			# Here base is the company currency
			# Total discount = Item row discounts (converted to base) + Header discount (already base)
			# row_discount_currency is SUM(qty * discount_amount) from PO Items
			# bade_amount and other fields are the parent level fields that have values in company currency
			row_discount_base = flt(po.row_discount_currency) * flt(po.conversion_rate)
			po_mrp_base = flt(po.po_mrp_currency) * flt(po.conversion_rate)
			po_discount = row_discount_base + flt(po.header_discount)
			actual_gross = flt(po.base_net_total) + po_discount
			
			# PI Amount = Grand Total * billing percentage
			billed_amount = flt(po.base_grand_total) * flt(po.per_billed) / 100
			
			received_qty = flt(po.total_qty) * flt(po.per_received) / 100
			remaining_qty = flt(po.total_qty) - received_qty

			total_discount += po_discount
			total_gross += actual_gross
			total_po_value += flt(po.base_grand_total)
			total_mrp += po_mrp_base
			total_billed += billed_amount
			total_received_qty += received_qty
			total_remaining_qty += remaining_qty
			total_pi_count += pi_count_map.get(po.name, 0)

		# Calculations
		# Discount % = (Total MRP - Total PO Value) * 100 / Total MRP
		overall_discount_pct = (((total_mrp - total_po_value) / total_mrp) * 100) if total_mrp > 0 else 0
		overall_pi_pct = (total_billed / total_po_value * 100) if total_po_value > 0 else 0

		# Format columns
		discount_stats = f"{flt(overall_discount_pct, 2)}%"

		formatted_pi_value = frappe.utils.fmt_money(total_billed, currency=company_currency)
		pi_stats = f"{formatted_pi_value} ({total_pi_count})"

		received_stats = f"{flt(total_received_qty, 2)} ({flt(total_remaining_qty, 2)})"

		data.append(
			{
				"supplier": supplier,
				"total_pos": total_po_count,
				"total_po_amount": flt(total_po_value, 2),
				"total_mrp": flt(total_mrp, 2),
				"discount_stats": discount_stats,
				"total_pi_amount": flt(total_billed, 2),
				"pi_percentage": flt(overall_pi_pct, 2),
				"received_stats": received_stats,
			}
		)

	return data


def get_conditions(filters):
	conditions = ""

	if filters.get("from_date"):
		conditions += " AND po.transaction_date >= %(from_date)s"

	if filters.get("to_date"):
		conditions += " AND po.transaction_date <= %(to_date)s"

	if filters.get("supplier"):
		conditions += " AND po.supplier = %(supplier)s"

	if filters.get("business_type") and filters.get("business_type") != "Both":
		conditions += " AND po.custom_type = %(business_type)s"

	return conditions
