# This file contains the monkey patch for item price override function
# It is used to add the filter so that only the IP that are Approved and enabled are considered anywhere.
import frappe
from frappe.query_builder.functions import IfNull
import json

from frappe.query_builder.functions import IfNull
from frappe.utils import flt

from erpnext.stock.get_item_details import check_packing_list,get_price_list_currency_and_exchange_rate,validate_conversion_rate,insert_item_price



def get_item_price(args, item_code, ignore_party=False, force_batch_no=False) -> list[dict]:
	"""
	Get name, price_list_rate from Item Price based on conditions
			Check if the desired qty is within the increment of the packing list.
	:param args: dict (or frappe._dict) with mandatory fields price_list, uom
			optional fields transaction_date, customer, supplier
	:param item_code: str, Item Doctype field item_code
	"""
	ip = frappe.qb.DocType("Item Price")
	query = (
		frappe.qb.from_(ip)
		.select(ip.name, ip.price_list_rate, ip.uom,ip.custom_buying_price,ip.custom_margin,ip.custom_discount_on,ip.custom_discount_percentage)
		.where(
			(ip.item_code == item_code)
			& (ip.price_list == args.get("price_list"))
			& (IfNull(ip.uom, "").isin(["", args.get("uom")]))
			& (ip.workflow_state == "Approved")
			& (ip.custom_disable == 0)
		)
		.orderby(ip.valid_from, order=frappe.qb.desc)
		.orderby(IfNull(ip.batch_no, ""), order=frappe.qb.desc)
		.orderby(ip.uom, order=frappe.qb.desc)
	)

	if force_batch_no:
		query = query.where(ip.batch_no == args.get("batch_no"))
	else:
		query = query.where(IfNull(ip.batch_no, "").isin(["", args.get("batch_no")]))

	if not ignore_party:
		if args.get("customer"):
			query = query.where(ip.customer == args.get("customer"))
		elif args.get("supplier"):
			query = query.where(ip.supplier == args.get("supplier"))
		else:
			query = query.where((IfNull(ip.customer, "") == "") & (IfNull(ip.supplier, "") == ""))

	if args.get("transaction_date"):
		query = query.where(
			(IfNull(ip.valid_from, "2000-01-01") <= args["transaction_date"])
			& (IfNull(ip.valid_upto, "2500-12-31") >= args["transaction_date"])
		)

	return query.run()

def get_price_list_rate_for(args, item_code):
	"""
	:param customer: link to Customer DocType
	:param supplier: link to Supplier DocType
	:param price_list: str (Standard Buying or Standard Selling)
	:param item_code: str, Item Doctype field item_code
	:param qty: Desired Qty
	:param transaction_date: Date of the price
	"""
	item_price_args = {
		"item_code": item_code,
		"price_list": args.get("price_list"),
		"customer": args.get("customer"),
		"supplier": args.get("supplier"),
		"uom": args.get("uom"),
		"transaction_date": args.get("transaction_date"),
		"batch_no": args.get("batch_no"),
	}

	item_price_data = None
	price_list_rate = get_item_price(item_price_args, item_code)
	if price_list_rate:
		desired_qty = args.get("qty")
		if desired_qty and check_packing_list(price_list_rate[0][0], desired_qty, item_code):
			item_price_data = price_list_rate
	else:
		for field in ["customer", "supplier"]:
			del item_price_args[field]

		general_price_list_rate = get_item_price(
			item_price_args, item_code, ignore_party=args.get("ignore_party")
		)

		if not general_price_list_rate and args.get("uom") != args.get("stock_uom"):
			item_price_args["uom"] = args.get("stock_uom")
			general_price_list_rate = get_item_price(
				item_price_args, item_code, ignore_party=args.get("ignore_party")
			)

		if general_price_list_rate:
			item_price_data = general_price_list_rate
	if item_price_data:
		if item_price_data[0][2] == args.get("uom"):
			return (item_price_data[0][0], item_price_data[0][1], item_price_data[0][3], item_price_data[0][4], item_price_data[0][5], item_price_data[0][6])
		elif not args.get("price_list_uom_dependant"):
			return (item_price_data[0][0], flt(item_price_data[0][1] * flt(args.get("conversion_factor", 1))), item_price_data[0][3] * flt(args.get("conversion_factor", 1)), item_price_data[0][4], item_price_data[0][5], item_price_data[0][6])
		else:
			return (item_price_data[0][0], item_price_data[0][1], item_price_data[0][3], item_price_data[0][4], item_price_data[0][5], item_price_data[0][6])
	return (None, None, None, None, None, None)

def get_price_list_rate(args, item_doc, out=None):
	if out is None:
		out = frappe._dict()

	meta = frappe.get_meta(args.parenttype or args.doctype)

	if meta.get_field("currency") or args.get("currency"):
		if not args.get("price_list_currency") or not args.get("plc_conversion_rate"):
			# if currency and plc_conversion_rate exist then
			# `get_price_list_currency_and_exchange_rate` has already been called
			pl_details = get_price_list_currency_and_exchange_rate(args)
			args.update(pl_details)

		if meta.get_field("currency"):
			validate_conversion_rate(args, meta)
		
		fetched_price = get_price_list_rate_for(args, item_doc.name)
		ip_name = fetched_price[0]
		price_list_rate = fetched_price[1]
		custom_list_price = fetched_price[2]
		custom_margin = fetched_price[3]
		custom_discount_on = fetched_price[4]
		custom_discount_percentage = fetched_price[5]

		# variant
		if price_list_rate is None and item_doc.variant_of:
			varient_rate = get_price_list_rate_for(args, item_doc.variant_of)
			ip_name = fetched_price[0]
			price_list_rate = varient_rate[1]
			custom_list_price = varient_rate[2]
			custom_margin = varient_rate[3]
			custom_discount_on = varient_rate[4]
			custom_discount_percentage = varient_rate[5]


		# insert in database
		if price_list_rate is None or frappe.db.get_single_value(
			"Stock Settings", "update_existing_price_list_rate"
		):
			insert_item_price(args)

		if price_list_rate is None:
			return out
		out.custom_ip_name = ip_name
		out.price_list_rate = flt(price_list_rate) * flt(args.plc_conversion_rate) / flt(args.conversion_rate)
		
		# Handle MRP conversion based on currency
		# MRP in Item Price is always in INR (company currency)
		# Store the original INR value in custom_mrpcompany_currency
		# Convert to transaction currency for custom_list_price
		company_currency = frappe.get_cached_value("Company", args.get("company"), "default_currency")
		transaction_currency = args.get("currency")
		
		# Store the original MRP in company currency (INR)
		out.custom_mrpcompany_currency = flt(custom_list_price)
		
		# If transaction currency is different from company currency, convert the MRP
		if transaction_currency and transaction_currency != company_currency:
			# Get the conversion rate from company currency to transaction currency
			# conversion_rate in args is from transaction currency to company currency
			# So we need to divide by conversion_rate to get from company to transaction currency
			conversion_rate = flt(args.get("conversion_rate", 1))
			if conversion_rate > 0:
				out.custom_list_price = flt(custom_list_price) / conversion_rate
			else:
				out.custom_list_price = flt(custom_list_price)
		else:
			# Same currency, no conversion needed
			out.custom_list_price = flt(custom_list_price)
		
		out.custom_margin = custom_margin
		out.custom_discount_on = custom_discount_on
		out.discount_percentage = custom_discount_percentage
		print("out",out)
		if frappe.db.get_single_value("Buying Settings", "disable_last_purchase_rate"):
			return out

		if (
			not args.get("is_internal_supplier")
			and not out.price_list_rate
			and args.transaction_type == "buying"
		):
			from erpnext.stock.doctype.item.item import get_last_purchase_details

			out.update(get_last_purchase_details(item_doc.name, args.name, args.conversion_rate))

	return out
