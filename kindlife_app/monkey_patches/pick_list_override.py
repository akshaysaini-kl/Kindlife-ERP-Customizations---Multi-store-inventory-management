import frappe
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	get_auto_batch_nos,
	get_picked_serial_nos,
)
from erpnext.stock.doctype.pick_list.pick_list import get_rejected_warehouses
from collections import OrderedDict, defaultdict
from frappe import _



def get_allowed_warehouses():
	"""Get warehouses marked as 'custom_is_new_warehouse', cached in frappe.local."""
	if not hasattr(frappe.local, "allowed_new_warehouses"):
		frappe.local.allowed_new_warehouses = frappe.get_all(
			"Warehouse", filters={"custom_is_new_warehouse": 1}, pluck="name"
		)
	return frappe.local.allowed_new_warehouses


def get_qc_warehouses():
	"""Get warehouses marked as 'custom_is_qc_warehouse', cached in frappe.local."""
	if not hasattr(frappe.local, "qc_warehouses"):
		frappe.local.qc_warehouses = frappe.get_all(
			"Warehouse", filters={"custom_is_qc_warehouse": 1}, pluck="name"
		)
	return frappe.local.qc_warehouses


def get_available_item_locations_for_batched_item(
	item_code,
	from_warehouses,
	consider_rejected_warehouses=False,
):
	locations = []
	data = get_auto_batch_nos(
		frappe._dict(
			{
				"item_code": item_code,
				"warehouse": from_warehouses,
				"based_on": frappe.db.get_single_value("Stock Settings", "pick_serial_and_batch_based_on"),
			}
		)
	)

	warehouse_wise_batches = frappe._dict()
	rejected_warehouses = get_rejected_warehouses()
	qc_warehouses = get_qc_warehouses()
	allowed_warehouses = get_allowed_warehouses()

	for d in data:
		if not consider_rejected_warehouses and rejected_warehouses and d.warehouse in rejected_warehouses + qc_warehouses:
			continue

		# Remove the warehouses that are not specifically marked for this
		if d.warehouse not in allowed_warehouses:
			continue

		if d.warehouse not in warehouse_wise_batches:
			warehouse_wise_batches.setdefault(d.warehouse, defaultdict(float))

		warehouse_wise_batches[d.warehouse][d.batch_no] += d.qty

	for warehouse, batches in warehouse_wise_batches.items():
		for batch_no, qty in batches.items():
			locations.append(
				frappe._dict(
					{
						"qty": qty,
						"warehouse": warehouse,
						"item_code": item_code,
						"batch_no": batch_no,
					}
				)
			)

	return locations


@frappe.whitelist()
def set_item_locations_with_warning(self, save=False):
	"""
	Override of PickList.set_item_locations to show warnings when items are removed 
	or quantities are reduced due to insufficient stock.
	"""
	from erpnext.stock.doctype.pick_list.pick_list import (
		get_available_item_locations,
		get_items_with_location_and_quantity,
	)
	from frappe.utils import flt
	from collections import OrderedDict
	
	# Store original items before processing to track changes
	# Group by item_code and reference (not warehouse) since system can pick from any warehouse
	original_items = {}
	for item in self.get("locations"):
		if not item.picked_qty:  # Only track items that haven't been picked yet
			key = (
				item.item_code,
				item.sales_order_item or item.material_request_item,
			)
			if key not in original_items:
				original_items[key] = {
					"item_code": item.item_code,
					"item_name": item.item_name,
					"qty": 0,
					"stock_qty": 0,
					"uom": item.uom,
					"sales_order": item.sales_order,
					"sales_order_item": item.sales_order_item,
					"material_request": item.material_request,
					"material_request_item": item.material_request_item,
				}
			original_items[key]["qty"] += flt(item.qty)
			original_items[key]["stock_qty"] += flt(item.stock_qty)
	
	# Call the original logic
	print("self.locations", self.locations)
	self.validate_for_qty()
	items = self.aggregate_item_qty()
	print("items", items)
	picked_items_details = self.get_picked_items_details(items)
	self.item_location_map = frappe._dict()

	from_warehouses = [self.parent_warehouse] if self.parent_warehouse else []
	if self.parent_warehouse:
		from frappe.utils.nestedset import get_descendants_of
		from_warehouses.extend(get_descendants_of("Warehouse", self.parent_warehouse))

	# Create replica before resetting, to handle empty table on update after submit.
	locations_replica = self.get("locations")

	# reset
	reset_rows = []
	for row in self.get("locations"):
		if not row.picked_qty:
			reset_rows.append(row)

	for row in reset_rows:
		self.remove(row)

	updated_locations = frappe._dict()
	len_idx = len(self.get("locations")) or 0
	for item_doc in items:
		item_code = item_doc.item_code

		self.item_location_map.setdefault(
			item_code,
			get_available_item_locations(
				item_code,
				from_warehouses,
				self.item_count_map.get(item_code),
				self.company,
				picked_item_details=picked_items_details.get(item_code),
				consider_rejected_warehouses=self.consider_rejected_warehouses,
			),
		)

		locations = get_items_with_location_and_quantity(item_doc, self.item_location_map, self.docstatus)
		print("locations---", locations)
		item_doc.idx = None
		item_doc.name = None

		for row in locations:
			location = item_doc.as_dict()
			location.update(row)
			key = (
				location.item_code,
				location.warehouse,
				location.uom,
				location.batch_no,
				location.serial_no,
				location.sales_order_item or location.material_request_item,
			)

			if key not in updated_locations:
				updated_locations.setdefault(key, location)
			else:
				updated_locations[key].qty += location.qty
				updated_locations[key].stock_qty += location.stock_qty

	for location in updated_locations.values():
		if location.picked_qty > location.stock_qty:
			location.picked_qty = location.stock_qty

		len_idx += 1
		location.idx = len_idx
		self.append("locations", location)

	# If table is empty on update after submit, set stock_qty, picked_qty to 0 so that indicator is red
	# and give feedback to the user. This is to avoid empty Pick Lists.
	if not self.get("locations") and self.docstatus == 1:
		for location in locations_replica:
			location.stock_qty = 0
			location.picked_qty = 0

			len_idx += 1
			location.idx = len_idx
			self.append("locations", location)

		frappe.msgprint(
			frappe._(
				"Please Restock Items and Update the Pick List to continue. To discontinue, cancel the Pick List."
			),
			title=frappe._("Out of Stock"),
			indicator="red",
		)

	# Track final items after processing
	# Group by item_code and reference (not warehouse) to match original_items grouping
	final_items = {}
	for item in self.get("locations"):
		if not item.picked_qty:  # Only track items that haven't been picked yet
			key = (
				item.item_code,
				item.sales_order_item or item.material_request_item,
			)
			if key not in final_items:
				final_items[key] = {
					"item_code": item.item_code,
					"item_name": item.item_name,
					"qty": 0,
					"stock_qty": 0,
					"uom": item.uom,
				}
			final_items[key]["qty"] += flt(item.qty)
			final_items[key]["stock_qty"] += flt(item.stock_qty)
	
	# Compare and build warning messages
	removed_items = []
	reduced_items = []
	print("original_items", original_items)
	print("final_items", final_items)
	for key, original_item in original_items.items():
		if key not in final_items:
			# Item was completely removed
			removed_items.append(original_item)
		else:
			# Check if quantity was reduced
			final_item = final_items[key]
			if flt(final_item["stock_qty"]) < flt(original_item["stock_qty"]):
				reduced_items.append({
					"item_code": original_item["item_code"],
					"item_name": original_item["item_name"],
					"original_qty": original_item["qty"],
					"final_qty": final_item["qty"],
					"original_stock_qty": original_item["stock_qty"],
					"final_stock_qty": final_item["stock_qty"],
					"uom": original_item["uom"],
					"sales_order": original_item.get("sales_order"),
					"sales_order_item": original_item.get("sales_order_item"),
					"material_request": original_item.get("material_request"),
				})
	
	# Show warnings if there are removed or reduced items
	if removed_items or reduced_items:
		warning_message = ""
		
		# Add scrollable container style for large datasets
		scrollable_style = "max-height: 400px; overflow-y: auto; margin-bottom: 20px;"
		
		if removed_items:
			warning_message += "<b>Items Removed (Insufficient Stock):</b><br><br>"
			warning_message += f"<div style='{scrollable_style}'>"
			warning_message += "<table class='table table-bordered table-hover'>"
			warning_message += "<thead style='position: sticky; top: 0; background-color: #f8f9fa; z-index: 1;'>"
			warning_message += "<tr><th>Item Code</th><th>Item Name</th><th>Requested Qty</th><th>UOM</th><th>Reference</th></tr>"
			warning_message += "</thead><tbody>"
			for item in removed_items:
				reference = ""
				if item.get("sales_order"):
					reference = f"SO: {item['sales_order']}"
				elif item.get("material_request"):
					reference = f"MR: {item['material_request']}"
				
				warning_message += f"<tr><td>{item['item_code']}</td><td>{item['item_name'] or ''}</td><td>{item['qty']}</td><td>{item['uom']}</td><td>{reference}</td></tr>"
			warning_message += "</tbody></table></div>"
		
		if reduced_items:
			warning_message += "<b>Items with Reduced Quantity:</b><br><br>"
			warning_message += f"<div style='{scrollable_style}'>"
			warning_message += "<table class='table table-bordered table-hover'>"
			warning_message += "<thead style='position: sticky; top: 0; background-color: #f8f9fa; z-index: 1;'>"
			warning_message += "<tr><th>Item Code</th><th>Item Name</th><th>Requested Qty</th><th>Available Qty</th><th>UOM</th><th>Reference</th></tr>"
			warning_message += "</thead><tbody>"
			for item in reduced_items:
				reference = ""
				if item.get("sales_order"):
					reference = f"SO: {item['sales_order']}"
				elif item.get("material_request"):
					reference = f"MR: {item.get('material_request', '')}"
				
				warning_message += f"<tr><td>{item['item_code']}</td><td>{item['item_name'] or ''}</td><td>{item['original_qty']}</td><td>{item['final_qty']}</td><td>{item['uom']}</td><td>{reference}</td></tr>"
			warning_message += "</tbody></table></div>"
		
		frappe.msgprint(
			warning_message,
			title=frappe._("Insufficient Stock Warning"),
			indicator="orange",
			as_list=False,
		)

	if save:
		self.save()
