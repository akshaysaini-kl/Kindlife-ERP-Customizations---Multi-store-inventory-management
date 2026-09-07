# Sales Order Server Script
# Event: Before Save
# This script automatically populates taxes table when taxes_and_charges is set but taxes table is empty

import frappe
from frappe import _
from erpnext.controllers.accounts_controller import get_taxes_and_charges


def so_validate(doc, method):
    # calculate_custom_discount(doc, method)
    set_warehouses_from_addresses(doc)
    set_sales_taxes(doc, method)
    calculate_custom_totals(doc)
    set_brand_fulfillment_fields(doc)



def set_brand_fulfillment_fields(doc):
	"""
	For B2C Sales Orders, auto-set `supplier` and `delivered_by_supplier`
	on each item whose Item master is brand-fulfilled (custom_fulfilled_by = 'Brand').
	Mirrors the logic in api/sales_order.py prepare_items.
	"""
	if (doc.get("custom_type") or "").upper() != "B2C":
		return

	for item in doc.items:
		# Read fulfillment type from Item master
		fulfillment_type = frappe.db.get_value(
			"Item", item.item_code, "custom_fulfilled_by"
		) or ""

		if fulfillment_type.lower() == "brand":
			item.custom_fulfilled_by = fulfillment_type
			item.delivered_by_supplier = 1

			# Set supplier only if not already set
			if not item.supplier:
				supplier = frappe.db.get_value(
					"Item Supplier",
					{"parent": item.item_code, "parenttype": "Item"},
					"supplier",
					order_by="idx asc",
				)
				# if not supplier:
				# 	frappe.throw(
				# 		_("Item {0} is Brand fulfilled but has no supplier defined in Item Supplier table.").format(
				# 			frappe.bold(item.item_code)
				# 		)
				# 	)
				item.supplier = supplier

		elif fulfillment_type.lower() == "warehouse":
			# Ensure warehouse items are not marked as drop-ship
			item.delivered_by_supplier = 0
			item.supplier = None


def set_warehouses_from_addresses(doc):
    """
    Set set_warehouse and custom_destination_warehouse from shipping_address_name and dispatch_address_name
    by checking the Dynamic Link table in the Address doctype.
    """
    if not doc.is_internal_customer:
        return
    if doc.shipping_address_name:
        shipping_warehouse = frappe.db.get_value(
            "Dynamic Link", 
            {"parent": doc.shipping_address_name, "parenttype": "Address", "link_doctype": "Warehouse"}, 
            "link_name"
        )
        if shipping_warehouse:
            doc.custom_destination_warehouse = shipping_warehouse
            # doc.set_warehouse = shipping_warehouse

    if doc.dispatch_address_name:
        dispatch_warehouse = frappe.db.get_value(
            "Dynamic Link", 
            {"parent": doc.dispatch_address_name, "parenttype": "Address", "link_doctype": "Warehouse"}, 
            "link_name"
        )
        if dispatch_warehouse:
            doc.set_warehouse = dispatch_warehouse

def calculate_custom_totals(doc):
    """
    Calculate custom_total_buying_price_without_discount for each item
    and custom_total_without_discount for the parent doc.
    """
    total_without_discount = 0
    for item in doc.items:
        # Calculate conversion factor from taxes
        igst = frappe.utils.flt(item.igst_rate)
        cgst = frappe.utils.flt(item.cgst_rate)
        sgst = frappe.utils.flt(item.sgst_rate)
        # We can either have igst or cgst/sgst
        conversion_factor = (igst + cgst + sgst) / 100.0

        # Calculate using the new formula
        # (price_list_rate * qty) / (1 + conversion_factor)
        try:
            item.custom_total_buying_price_without_discount = (frappe.utils.flt(item.price_list_rate) * frappe.utils.flt(item.qty)) / (1 + conversion_factor)
        except ZeroDivisionError:
            item.custom_total_buying_price_without_discount = (frappe.utils.flt(item.price_list_rate) * frappe.utils.flt(item.qty))


        total_without_discount += item.custom_total_buying_price_without_discount
    
    doc.custom_total_without_discount = total_without_discount



def set_sales_taxes(doc, method):
    """
    Auto-populate taxes table if taxes_and_charges is set but taxes table is empty
    This handles cases like data import where client-side JS doesn't execute
    """
    print("here")
    # Check if taxes_and_charges is set but taxes table is empty
    if doc.taxes_and_charges and not doc.taxes:
        try:
            # Get the master doctype for taxes_and_charges field
            taxes_field = frappe.get_meta(doc.doctype).get_field("taxes_and_charges")
            if not taxes_field or not taxes_field.options:
                return
            
            master_doctype = taxes_field.options
            
            # Call the same method used by the JavaScript function
            taxes_data = get_taxes_and_charges(master_doctype, doc.taxes_and_charges)
            print("taxes_data",taxes_data)
            if taxes_data:
                # Clear existing taxes (if any)
                doc.taxes = []
                
                # Add each tax row to the taxes table
                for tax_row in taxes_data:
                    doc.append("taxes", tax_row)
                
                # Recalculate taxes and totals
                doc.calculate_taxes_and_totals()
                
                frappe.logger().info(f"Auto-populated {len(taxes_data)} tax rows for Sales Order {doc.name}")
                
        except Exception as e:
            frappe.logger().error(f"Error auto-populating taxes for Sales Order {doc.name}: {str(e)}")
            # Don't raise the error to avoid blocking the save operation
            # Just log it for debugging purposes


def calculate_custom_discount(doc, method):
    """
    Calculate discount based on custom_discount_on field (MRP or Selling Price)
    This ensures that data import or server-side creation works correctly
    """
    for item in doc.items:
        if item.custom_discount_on == "MRP" and item.custom_list_price > 0:
            # Calculate discount amount based on MRP
            discount_percentage = frappe.utils.flt(item.discount_percentage)
            discount_amount = frappe.utils.flt(item.custom_list_price) * (discount_percentage / 100.0)
            
            # Update item values
            item.discount_amount = discount_amount
            
            # Calculate new rate
            rate = frappe.utils.flt(item.custom_list_price - discount_amount, item.precision("rate"))
            item.rate = rate
            
            # Update other values
            item.amount = frappe.utils.flt(rate * item.qty, item.precision("amount"))
            item.net_rate = rate
            item.net_amount = item.amount
            
            # Update base values (assuming conversion_rate is available in parent doc)
            conversion_rate = doc.conversion_rate or 1.0
            item.base_rate = frappe.utils.flt(rate * conversion_rate, item.precision("base_rate"))
            item.base_amount = frappe.utils.flt(item.amount * conversion_rate, item.precision("base_amount"))
            item.base_net_rate = item.base_rate
            item.base_net_amount = item.base_amount