# Copyright (c) 2026, Kindlife and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 120
		},
		{
			"label": _("Date"),
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 120
		},
		{
			"label": _("Business Type"),
			"fieldname": "business_type",
			"fieldtype": "Data",
			"width": 80
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Fulfillment Type"),
			"fieldname": "fulfillment_type",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 80
		},
		{
			"label": _("MRP (Co Currency)"),
			"fieldname": "mrp",
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"label": _("Selling Rate (Inc. Tax)"),
			"fieldname": "selling_rate_inc_tax",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Margin (From Item)"),
			"fieldname": "custom_margin",
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"label": _("Selling Rate (Exc. Tax)"),
			"fieldname": "selling_rate_exc_tax",
			"fieldtype": "Currency",
			"width": 150
		},
		
		{
			"label": _("Additional Discount %"),
			"fieldname": "discount_percentage",
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"label": _("Buying Rate (COGS)"),
			"fieldname": "buying_rate",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Revenue (Net)"),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("COGS"),
			"fieldname": "cogs",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Gross Margin"),
			"fieldname": "gross_margin",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Gross Margin %"),
			"fieldname": "gross_margin_pct",
			"fieldtype": "Percent",
			"width": 150
		},
		{
			"label": _("Cost Source"),
			"fieldname": "cost_source",
			"fieldtype": "Data",
			"width": 120
		}
	]

def get_data(filters):
	conditions = get_conditions(filters)
	
	# Fetch Sales Invoice Items
	# We also fetch SO Item details to link to Purchase Orders for Brand items
	# And DN Item details for Warehouse items (if cost not on Invoice)
	data = frappe.db.sql(f"""
		SELECT
			si.name as sales_invoice,
			si.posting_date as date,
			si.customer,
			si.custom_type as business_type,
			sii.item_code,
			sii.item_name,
			sii.qty,
			sii.rate as rate_inc_tax,
			sii.base_net_rate as rate_exc_tax,
			sii.incoming_rate as sii_incoming_rate,
			sii.custom_list_price as mrp,
			sii.custom_margin,
			sii.discount_percentage,
			sii.so_detail,
			sii.dn_detail,
			dni.incoming_rate as dni_incoming_rate,
			item.custom_fulfilled_by,
			item.valuation_rate as item_master_rate
		FROM
			`tabSales Invoice` si
		INNER JOIN
			`tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN
			`tabItem` item ON item.name = sii.item_code
		LEFT JOIN
			`tabDelivery Note Item` dni ON dni.name = sii.dn_detail
		WHERE
			si.docstatus = 1
			{conditions}
		ORDER BY
			si.posting_date DESC, si.name DESC
	""", filters, as_dict=1)
	
	result = []
	
	# Collect SO Item names to fetch PO details in bulk
	so_items = [d.so_detail for d in data if d.so_detail]
	
	# Map SO Item to PO Item Rate
	so_item_po_map = {}
	if so_items:
		# Helper query to get PO rate linked to SO item
		po_rates = frappe.db.sql("""
			SELECT
				poi.sales_order_item,
				poi.rate
			FROM
				`tabPurchase Order Item` poi
			WHERE
				poi.sales_order_item IN %s
				AND poi.docstatus = 1
		""", (so_items,), as_dict=1)
		
		for p in po_rates:
			so_item_po_map[p.sales_order_item] = flt(p.rate)

	for row in data:
		buying_rate = 0.0
		cost_source = ""
		fulfillment_type = row.get("custom_fulfilled_by") or "Warehouse"
		
		# Logic for Cost Determination
		if fulfillment_type.lower() == "brand" and row.so_detail and row.so_detail in so_item_po_map:
			buying_rate = so_item_po_map[row.so_detail]
			cost_source = "Purchase Order"
		else:
			# Fallback or Warehouse Logic
			# 1. Check Invoice Cost (if Update Stock is checked)
			if flt(row.sii_incoming_rate) > 0:
				buying_rate = flt(row.sii_incoming_rate)
				cost_source = "Invoice Cost"
			# 2. Check Delivery Note Cost (if linked)
			elif flt(row.dni_incoming_rate) > 0:
				buying_rate = flt(row.dni_incoming_rate)
				cost_source = "Delivery Note Cost"
			# 3. Fallback to Item Master
			else:
				buying_rate = flt(row.item_master_rate)
				cost_source = "Item Master (Est)"
		
		# Revenue (Displayed) = Net (without GST)
		revenue_display = flt(row.qty) * flt(row.rate_exc_tax)
		
		# Margin Calculation (Using Selling Rate Inc Tax as per requirement)
		revenue_inc_tax = flt(row.qty) * flt(row.rate_inc_tax)
		cogs = flt(row.qty) * buying_rate
		
		gross_margin = revenue_inc_tax - cogs
		# Margin % based on the inclusive revenue to stay consistent with the absolute margin calculation method
		gross_margin_pct = (gross_margin / revenue_inc_tax * 100) if revenue_inc_tax != 0 else 0.0
		
		result.append({
			"sales_invoice": row.sales_invoice,
			"date": row.date,
			"customer": row.customer,
			"business_type": row.business_type,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"fulfillment_type": fulfillment_type,
			"qty": row.qty,
			"mrp": row.mrp,
			"selling_rate_inc_tax": row.rate_inc_tax,
			"selling_rate_exc_tax": row.rate_exc_tax,
			"revenue": revenue_display,
			"discount_percentage": row.discount_percentage,
			"custom_margin": row.custom_margin,
			"buying_rate": buying_rate,
			"cogs": cogs,
			"gross_margin": gross_margin,
			"gross_margin_pct": gross_margin_pct,
			"cost_source": cost_source
		})
		
	return result

def get_conditions(filters):
	conditions = []
	
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
	if filters.get("custom_type"):
		conditions.append("si.custom_type = %(custom_type)s")
	if filters.get("item_code"):
		conditions.append("sii.item_code = %(item_code)s")
	if filters.get("fulfillment_type"):
		conditions.append("item.custom_fulfilled_by = %(fulfillment_type)s")
	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		
	return "AND " + " AND ".join(conditions) if conditions else ""
