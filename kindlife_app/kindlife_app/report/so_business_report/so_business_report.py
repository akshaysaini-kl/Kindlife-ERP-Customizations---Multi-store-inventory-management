# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, fmt_money


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	return [
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 240,
		},
		{
			"label": _("No of SO's"),
			"fieldname": "total_sos",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Total MRP Value"),
			"fieldname": "total_mrp",
			"fieldtype": "Currency",
			"width": 170,
			"precision": 2
		},
		{
			"label": _("Total SO Value"),
			"fieldname": "total_so_value",
			"fieldtype": "Currency",
			"width": 170,
			"precision": 2
		},
		{
			"label": _("Discount %"),
			"fieldname": "discount_stats",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("SI Value"),
			"fieldname": "total_si_amount",
			"fieldtype": "Currency",
			"width": 140,
			"precision": 2
		},
		{
			"label": _("SI% of SO Value"),
			"fieldname": "si_percentage",
			"fieldtype": "Percent",
			"width": 145,
			"precision": 2
		},
		{
			"label": _("COGS"),
			"fieldname": "total_cogs",
			"fieldtype": "Currency",
			"width": 150,
			"precision": 2
		},
		{
			"label": _("Profit"),
			"fieldname": "total_profit",
			"fieldtype": "Currency",
			"width": 120,
			"precision": 2
		},
		{
			"label": _("Profit% from SO Value"),
			"fieldname": "profit_percentage",
			"fieldtype": "Data",
			"width": 180,
		},
	]



def get_data(filters):
	conditions = get_conditions(filters)
	company_currency = frappe.get_cached_value(
		"Company", frappe.db.get_default("company"), "default_currency"
	)

	# Fetch Sales Orders first
	# Filter: Must have Sales Invoice (per_billed > 0) AND Delivery Note (per_delivered > 0)
	sales_orders = frappe.db.sql(
		f"""
		SELECT
			so.name,
			so.customer,
			so.customer_name,
			so.base_grand_total,
			so.base_net_total,
			so.per_billed,
			so.base_discount_amount as header_discount,
			so.conversion_rate
		FROM
			`tabSales Order` so
		WHERE
			so.docstatus = 1
			AND so.per_billed > 0
			{conditions}
		""",
		filters,
		as_dict=1,
	)

	if not sales_orders:
		return []

	so_names = [so.name for so in sales_orders]
	
	# Fetch all items for these SOs
	so_items = frappe.db.sql(
		"""
		SELECT
			name, parent, item_code, qty, rate, base_rate, amount, base_amount,
			net_amount, base_net_amount,
			price_list_rate, base_price_list_rate, custom_list_price,
			discount_amount
		FROM
			`tabSales Order Item`
		WHERE
			parent IN %s
		""",
		(so_names,),
		as_dict=1,
	)

	so_item_names = [item.name for item in so_items]

	# Fetch Linked Documents for Costing
	
	# 1. Sales Invoice Items (Priority 1 for Stock)
	si_items = frappe.db.sql("""
		SELECT so_detail, incoming_rate, base_net_rate 
		FROM `tabSales Invoice Item` 
		WHERE so_detail IN %s AND docstatus=1
	""", (so_item_names,), as_dict=1)
	si_map = {}
	for si in si_items:
		if si.so_detail not in si_map: si_map[si.so_detail] = []
		si_map[si.so_detail].append(si)

	# 2. Purchase Order Items (Priority 1 for Brand/DropShip)
	po_items = frappe.db.sql("""
		SELECT sales_order_item, rate 
		FROM `tabPurchase Order Item` 
		WHERE sales_order_item IN %s AND docstatus=1
	""", (so_item_names,), as_dict=1)
	po_map = {d.sales_order_item: d.rate for d in po_items}

	# 3. Delivery Note Items (Priority 2 for Stock)
	dn_items = frappe.db.sql("""
		SELECT so_detail, incoming_rate 
		FROM `tabDelivery Note Item` 
		WHERE so_detail IN %s AND docstatus=1
	""", (so_item_names,), as_dict=1)
	dn_map = {}
	for dn in dn_items:
		if dn.so_detail not in dn_map: dn_map[dn.so_detail] = []
		dn_map[dn.so_detail].append(dn)

	# Group items by SO for easy access
	so_items_map = {}
	for item in so_items:
		if item.parent not in so_items_map:
			so_items_map[item.parent] = []
		so_items_map[item.parent].append(item)

	# Aggregate by customer
	customer_data = {}
	for so in sales_orders:
		customer = so.customer
		if customer not in customer_data:
			customer_data[customer] = {
				"customer": customer,
				"total_sos": 0,
				"total_mrp": 0,
				"total_so_value": 0,
				"total_si_amount": 0,
				"total_cogs": 0,
				"total_discount": 0,
				"total_net_value": 0,
				"total_billed_profit": 0,
				"total_billed_net_value": 0,
			}
		
		res = customer_data[customer]
		res["total_sos"] += 1
		# Sales Value
		res["total_so_value"] += flt(so.base_grand_total)
		res["total_net_value"] += flt(so.base_net_total)
		
		# SI Amount
		si_amount = flt(so.base_grand_total) * flt(so.per_billed) / 100
		res["total_si_amount"] += si_amount

		# Process items for COGS, MRP, and Discount
		items = so_items_map.get(so.name, [])
		current_so_cogs = 0.0
		for item in items:
			# MRP (converting to base)
			res["total_mrp"] += flt(item.custom_list_price) * flt(item.qty) * flt(so.conversion_rate)
			
			# Discount
			# Explicit Discount (Gap B - what the user sees)
			res["total_discount"] += flt(item.discount_amount) * flt(item.qty) * flt(so.conversion_rate)

			# COGS Logic
			buying_rate = 0.0
			
			# Priority 1: Brand (PO) - If linked PO exists, use it
			if item.name in po_map:
				buying_rate = flt(po_map[item.name])
			else:
				# Priority 2: Invoice Stock
				sis = si_map.get(item.name, [])
				# In case of multiple SIs for same SO Item, take the average
				valid_sis = [flt(s.incoming_rate) for s in sis if flt(s.incoming_rate) > 0]
				if valid_sis:
					buying_rate = sum(valid_sis) / len(valid_sis)
				else:
					# Priority 3: Delivery Note Stock
					dns = dn_map.get(item.name, [])
					valid_dns = [flt(d.incoming_rate) for d in dns if flt(d.incoming_rate) > 0]
					if valid_dns:
						buying_rate = sum(valid_dns) / len(valid_dns)
					else:
						# Priority 4: Missing
						buying_rate = 0.0
			
			item_cogs = buying_rate * flt(item.qty)
			res["total_cogs"] += item_cogs
			current_so_cogs += item_cogs

		# Add Header Discount
		res["total_discount"] += flt(so.header_discount)
		
		# Billed Profit Calculation
		if flt(so.per_billed) > 0:
			billed_ratio = flt(so.per_billed) / 100.0
			so_net_revenue = flt(so.base_net_total)
			
			# Calculate Profit for the WHOLE SO first
			so_full_profit = so_net_revenue - current_so_cogs
			
			# Logic: Profit is purely based on billed items
			# We assume billed items have proportional profit to the whole SO
			so_billed_profit = so_full_profit * billed_ratio
			so_billed_net_value = so_net_revenue * billed_ratio
			
			res["total_billed_profit"] += so_billed_profit
			res["total_billed_net_value"] += so_billed_net_value

	data = []
	for customer, vals in customer_data.items():
		# SI %
		si_percentage = (vals["total_si_amount"] / vals["total_so_value"] * 100) if vals["total_so_value"] > 0 else 0
		
		# Profit Logic based on BILLED portion
		# Note: COGS column still shows TOTAL COGS for all items in SO (as requested)
		# But Profit column shows profit only for billed items
		
		total_profit_val = flt(vals["total_billed_profit"])
		billed_net_revenue = flt(vals["total_billed_net_value"])

		# Formatting Profit
		# If nothing is billed, profit is 0 (or -)
		if billed_net_revenue <= 0 and total_profit_val == 0:
			total_profit = fmt_money(0, currency=company_currency)
			profit_percentage = "0%"
		else:
			total_profit = fmt_money(total_profit_val, currency=company_currency)
			
			# Profit % based on Billed Revenue
			profit_pct_val = (total_profit_val / billed_net_revenue * 100) if billed_net_revenue > 0 else 0
			profit_percentage = f"{flt(profit_pct_val, 2)}%"
		
		# Discount % = (Total MRP - Total SO Value) * 100 / Total MRP
		overall_discount_pct = (((vals["total_mrp"] - vals["total_so_value"]) / vals["total_mrp"]) * 100) if vals["total_mrp"] > 0 else 0
		discount_stats = f"{flt(overall_discount_pct, 2)}%"

		data.append({
			"customer": customer,
			"total_sos": vals["total_sos"],
			"total_mrp": flt(vals["total_mrp"], 2),
			"total_so_value": flt(vals["total_so_value"], 2),
			"discount_stats": discount_stats,
			"total_si_amount": flt(vals["total_si_amount"], 2),
			"si_percentage": flt(si_percentage, 2),
			"total_cogs": flt(vals["total_cogs"], 2),
			"total_profit": flt(total_profit_val, 2),
			"profit_percentage": profit_percentage,
		})

	return data


def get_conditions(filters):
	conditions = ""

	if filters.get("from_date"):
		conditions += " AND so.transaction_date >= %(from_date)s"

	if filters.get("to_date"):
		conditions += " AND so.transaction_date <= %(to_date)s"

	if filters.get("customer"):
		conditions += " AND so.customer = %(customer)s"

	if filters.get("business_type") and filters.get("business_type") != "Both":
		conditions += " AND so.custom_type = %(business_type)s"

	return conditions
