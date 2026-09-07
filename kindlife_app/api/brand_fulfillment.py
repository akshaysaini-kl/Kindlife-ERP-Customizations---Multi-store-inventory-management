# brand_fulfillment.py
# API and scheduled methods for Brand fulfillment via Purchase Orders

import frappe
from frappe import _
from frappe.utils import nowdate, today, add_days, flt, get_url
import json
import requests
from kindlife_app.services.cscart_service import CS_CART_CONSTANTS
from kindlife_app.api.sales_order import get_address
from frappe.utils.password import get_decrypted_password



def create_purchase_orders_for_brand_items():
	"""
	Scheduled method (Daily Cron Job)
	Creates Purchase Orders for pending Sales Order items with fulfillment_type = "Brand"
	Groups items by supplier and creates one PO per supplier
	"""
	try:

		# Get pending SO items with Brand fulfillment
		pending_items = get_pending_brand_fulfillment_items()
		
		if not pending_items:
			frappe.logger().info("No pending brand fulfillment items found")
			return
		
		# Group items by supplier
		supplier_items = group_items_by_supplier(pending_items)
		
		# Create PO for each supplier
		created_pos = []

		for supplier, items in supplier_items.items():
			try:
				po = create_purchase_order(supplier, items)
				created_pos.append(po.name)
				
				# Update Sales Order Items with PO reference
				update_sales_order_items_with_po(items, po.name)
				frappe.logger().info(f"Updated items for PO {po.name}")
				
			except Exception as e:
				frappe.log_error(
					message=f"Error processing brand fulfillment for supplier {supplier}: {str(e)}\n{frappe.get_traceback()}",
					title="Brand Fulfillment Process Error"
				)
		
		frappe.db.commit()
		
		# Trigger sync to external system for newly created POs
		if created_pos:
			sync_po_list_to_external(created_pos)
		
		frappe.logger().info(f"Created {len(created_pos)} Purchase Orders for brand fulfillment: {created_pos}")
		
		return {
			"status": "success",
			"message": f"Created {len(created_pos)} Purchase Orders",
			"purchase_orders": created_pos
		}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Brand Fulfillment Cron Job Failed"
		)
		return {
			"status": "error",
			"message": str(e)
		}


def get_pending_brand_fulfillment_items():
	"""
	Get all Sales Order Items that:
	- Are from confirmed Sales Orders (docstatus = 1)
	- Have fulfillment_type = "Brand" on Item master
	- Don't have a Purchase Order linked yet
	- Are not fully delivered
	"""
	items = frappe.db.sql("""
		SELECT 
			soi.name as so_item_name,
			soi.parent as sales_order,
			soi.item_code,
			soi.item_name,
			soi.qty,
			soi.delivered_qty,
			soi.rate,
			soi.warehouse,
			soi.delivery_date,
			soi.custom_shipment_id,
			soi.custom_shipment_document,
			so.transaction_date,
			so.customer,
			so.company,
			so.po_no,
			item.custom_fulfilled_by,
			item.custom_b2c_product_id
		FROM `tabSales Order Item` soi
		INNER JOIN `tabSales Order` so ON so.name = soi.parent
		INNER JOIN `tabItem` item ON item.name = soi.item_code
		WHERE 
			so.customer = %s
			AND so.status NOT IN ('Closed', 'Completed', 'Cancelled')
			AND TRIM(LOWER(soi.custom_fulfilled_by)) = 'brand'
			AND (soi.purchase_order IS NULL OR soi.purchase_order = '')
			AND soi.qty > soi.delivered_qty
			AND (soi.custom_shipment_id IS NOT NULL AND soi.custom_shipment_id != '')
		ORDER BY so.transaction_date ASC, soi.item_code
	""", (CS_CART_CONSTANTS["CUSTOMER_NAME"],), as_dict=True)
	return items


def group_items_by_supplier(items):
	"""
	Group items by their supplier
	Gets supplier from Item's "Item Supplier" child table (first supplier)
	"""
	supplier_groups = {}
	
	for item in items:
		supplier = get_item_supplier(item.item_code)
		
		if not supplier:
			frappe.log_error(
				message=f"No supplier found for item {item.item_code} in SO {item.sales_order}",
				title="Brand Fulfillment - Missing Supplier"
			)
			continue
		
		if supplier not in supplier_groups:
			supplier_groups[supplier] = []
		
		supplier_groups[supplier].append(item)
	
	return supplier_groups


def get_item_supplier(item_code):
	"""
	Get the default supplier from Item Supplier child table.
	Prioritizes the row marked as 'custom_default_supplier'.
	If no default is marked, falls back to the first row (idx ASC).
	"""
	supplier = frappe.db.get_value(
		"Item Supplier",
		{"parent": item_code},
		"supplier",
		order_by="custom_default_supplier DESC, idx ASC"
	)
	
	return supplier


def create_purchase_order(supplier, items):
	"""
	Create Purchase Order for brand fulfillment items
	"""
	if not items:
		frappe.throw(_("No items to create Purchase Order"))
	
	# Get company from first item
	company = items[0].get('company')
	
	# Prepare PO items
	po_items = []
	for item in items:
		po_items.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"qty": flt(item.qty) - flt(item.delivered_qty),
			"rate": item.rate or 0,
			"schedule_date":  add_days(today(), 7),
			"warehouse": item.warehouse,
			
			# Link to Sales Order
			"sales_order": item.sales_order,
			"sales_order_item": item.so_item_name,
			
			# Custom fields
			"custom_fulfilled_by": "Brand",
			"custom_shipment_id": item.custom_shipment_id,
			"custom_shipment_document": item.custom_shipment_document,
			
			# Drop ship field
			# This field is in item level, is only visile if it is checked
			# The Make PR button is hidden if all the items have are checked
			"delivered_by_supplier": 1,
		})
	
	# Fetch the Supplier's default price list BEFORE insert
	# (mirrors what the UI does via erpnext.accounts.party.get_party_details → set_price_list)
	supplier_price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")

	# Create Purchase Order
	po = frappe.get_doc({
		"doctype": "Purchase Order",
		"supplier": supplier,
		"company": company,
		"transaction_date": today(),
		"schedule_date": add_days(today(), 7),
		
		# Drop ship fields
		# This field is in the Drop Ship tab
		# The drop ship tab is only visible if this field is filled
		"customer": CS_CART_CONSTANTS["CUSTOMER_NAME"],
		
		# Set buying price list from supplier's default (same as UI flow)
		"buying_price_list": supplier_price_list,
		
		# Custom fields to track brand fulfillment
		"custom_fulfilled_by": "Brand",
		"custom_auto_created": 1,
		"custom_type": "B2C",
		"custom_is_brand_fulfilled": 1,
		
		"items": po_items,
		
		# Additional settings
		"apply_discount_on": "Grand Total",
	})
	
	po.insert(ignore_permissions=True, ignore_mandatory=True)
	
	# Conditionally Auto-submit the PO
	if frappe.db.get_single_value("CS Cart Settings", "auto_submit_po"):
		if supplier_price_list and supplier_price_list.strip().lower() != "default price list":
			from frappe.model.workflow import apply_workflow
			
			try:
				apply_workflow(po, "Submit for approval")
				apply_workflow(po, "Approve")
				frappe.logger().info(f"Auto-submitted PO {po.name} via Workflow for supplier {supplier}")
			except Exception as e:
				frappe.logger().error(f"Failed to auto-submit PO {po.name} via Workflow: {str(e)}")
		else:
			frappe.logger().info(f"Kept PO {po.name} in Draft for supplier {supplier} due to Price List condition: {supplier_price_list}")
	else:
		frappe.logger().info(f"Kept PO {po.name} in Draft for supplier {supplier} because auto-submit is disabled in settings")
	
	
	frappe.logger().info(f"Created Purchase Order {po.name} for supplier {supplier} with {len(po_items)} items")
	
	return po


def update_sales_order_items_with_po(items, po_name):
	"""
	Update Sales Order Items with Purchase Order reference
	"""
	for item in items:
		frappe.db.set_value(
			"Sales Order Item",
			item.so_item_name,
			"purchase_order",
			po_name,
			update_modified=False
		)


@frappe.whitelist()
def manually_trigger_brand_fulfillment():
	"""
	Manual API endpoint to trigger brand fulfillment PO creation
	Can be called from UI or external systems
	"""
	return create_purchase_orders_for_brand_items()


@frappe.whitelist()
def get_brand_fulfillment_status():
	"""
	Get status of brand fulfillment items
	Shows pending items grouped by supplier
	"""
	pending_items = get_pending_brand_fulfillment_items()
	
	if not pending_items:
		return {
			"status": "success",
			"message": "No pending brand fulfillment items",
			"pending_count": 0,
			"suppliers": []
		}
	
	# Group by supplier for reporting
	supplier_groups = group_items_by_supplier(pending_items)
	
	supplier_summary = []
	for supplier, items in supplier_groups.items():
		total_qty = sum(flt(item.qty) - flt(item.delivered_qty) for item in items)
		total_amount = sum((flt(item.qty) - flt(item.delivered_qty)) * flt(item.rate) for item in items)
		
		supplier_summary.append({
			"supplier": supplier,
			"item_count": len(items),
			"total_qty": total_qty,
			"total_amount": total_amount,
			"items": [
				{
					"item_code": item.item_code,
					"sales_order": item.sales_order,
					"qty": flt(item.qty) - flt(item.delivered_qty)
				}
				for item in items
			]
		})
	
	return {
		"status": "success",
		"pending_count": len(pending_items),
		"suppliers": supplier_summary
	}

def sync_po_list_to_external(po_names):
	"""
	Triggers sync for a list of Purchase Order names.
	Collects unique Sales Orders from these POs and triggers sync for each.
	"""
	sales_orders = set()
	
	for po_name in po_names:
		try:
			# Make list of all unique SOs
			po_items = frappe.db.get_all("Purchase Order Item", filters={"parent": po_name}, fields=["sales_order"])
			for item in po_items:
				if item.sales_order:
					sales_orders.add(item.sales_order)
		except Exception as e:
			frappe.log_error(f"Error processing PO {po_name} for sync: {str(e)}", "PO Sync Error")
	
	frappe.logger().info(f"Unique Sales Orders to sync: {sales_orders}")
	
	for so_name in sales_orders:
		# Now iterate over SOs and sync them
		sync_sales_order_to_external(so_name)



def sync_sales_order_to_external(so_name):
	"""
	Collects details for a Sales Order and sends to external API.
	Includes both Brand (PO) and Warehouse (Pick List) fulfilled items.
	"""
	try:
		# Get SO details
		so_doc = frappe.get_doc("Sales Order", so_name)
		
		# Get details of payload to send
		payload = get_sales_order_sync_payload(so_doc)
		
		# Send payload to api
		send_sync_request(so_doc.name, payload)
	except Exception as e:
		frappe.log_error(f"Error syncing Sales Order {so_name}: {str(e)}\n{frappe.get_traceback()}", "SO Sync Error")


def get_sales_order_sync_payload(doc):
	"""
	Prepares the payload for a Sales Order Sync.
	Iterates through all Sales Order Items and determines fulfillment details.
	"""
	items_data = []
	
	for item in doc.items:
		payload_supplier = None
		payload_purchase_order = None
		payload_warehouse = None
		payload_pick_list = None
		logistic_partner = None
		
		# 1. Determine Fulfillment Type
		fulfillment_type = item.get("custom_fulfilled_by")
		
		if fulfillment_type == "Brand":
			# Brand Fulfillment
			payload_purchase_order = item.purchase_order
			# Get supplier logistics partner
			if payload_purchase_order:
				payload_supplier = frappe.db.get_value("Purchase Order", payload_purchase_order, "supplier")
				if payload_supplier:
					logistic_partner = frappe.db.get_value("Supplier", payload_supplier, "custom_default_logistic_partner")
		
		else:
			# Warehouse Fulfillment
			pick_list_item = frappe.db.get_value(
				"Pick List Item", 
				{"sales_order_item": item.name, "docstatus": ["!=", 2]}, 
				["parent"], 
				as_dict=True
			)
			
			if pick_list_item:
				payload_pick_list = pick_list_item.parent
			
			# Set Warehouse
			payload_warehouse = item.warehouse
			
			# Fetch Logistic Partner from Warehouse
			if payload_warehouse:
				logistic_partner = frappe.db.get_value("Warehouse", payload_warehouse, "custom_default_logistic_partner")

		# Fetch Item B2C ID
		product_code = frappe.db.get_value("Item", item.item_code, "custom_b2c_product_id")

		items_data.append({
			"custom_default_logistic_partner": logistic_partner,
			"supplier": payload_supplier,
			"purchase_order": payload_purchase_order,
			"warehouse": payload_warehouse,
			"pick_list": payload_pick_list,
			"item_code": item.item_code,
			"product_code": product_code,
			"qty": flt(item.qty),
			"shipment_id": item.get("custom_shipment_id") 
		})

	# Construct Final Payload
	payload = [{
		"sales_order_id": doc.name,
		"order_id": doc.po_no,
		"so_date": doc.transaction_date,
		"items": items_data
	}]
	
	frappe.logger().info(f"Payload: {frappe.as_json(payload)}")

	return payload


def send_sync_request(doc_name, payload):
	"""
	Sends prepared payload to the external API.
	"""
	base_url = frappe.get_site_config().get("cscart_base_url") 
	endpoint = "KlSalesOrderUpdateErpHook"
	url = f"{base_url}/api/{endpoint}"
	api_key = get_decrypted_password("CS Cart Settings", "CS Cart Settings", "api_token", raise_exception=False)
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json"
	}

	if not base_url or not endpoint or not api_key:
		frappe.throw("CS Cart Base URL or Endpoint or API Key not configured")

	try:
		frappe.logger().info(f"Sending Payload for {doc_name}: {frappe.as_json(payload)}")
		response = requests.post(url, headers=headers, data=frappe.as_json(payload), timeout=30)
		
		if response.status_code == 200:
			frappe.logger().info(f"Sync Successful for {doc_name}: {response.text}")
		else:
			frappe.log_error(
				message=f"Sync Failed for {doc_name}. Status: {response.status_code}\nResponse: {response.text}\nPayload: {frappe.as_json(payload)}",
				title=f"External Sync Failed: {doc_name}"
			)
			
	except Exception as e:
		frappe.log_error(
			message=f"Sync Request Error for {doc_name}: {str(e)}\n{frappe.get_traceback()}",
			title="External Sync Request Error"
		)

