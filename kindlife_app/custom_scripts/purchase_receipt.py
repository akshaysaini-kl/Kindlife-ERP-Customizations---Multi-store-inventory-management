import frappe
from frappe.utils import cint, flt, get_datetime, getdate, nowdate
from frappe import _, bold # 'bold' is used in your helper function.
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt as OriginalPurchaseReceipt
from erpnext.controllers.buying_controller import BuyingController
from frappe.model.mapper import get_mapped_doc
from erpnext.stock.serial_batch_bundle import (
	SerialBatchCreation,
	get_batches_from_bundle,
	get_serial_nos_from_bundle,
)

class PurchaseReceiptExtends(OriginalPurchaseReceipt):
	def validate(self):
		self.set_warehouses_from_delivery_note()
		super().validate()
		# only run batch‐no check when workflow_state has changed Pending Putaway
		if (self.has_value_changed("workflow_state") and self.workflow_state == "Pending Putaway"):
			self.check_batch_no()


	def check_batch_no(self):
		missing_batch_items = []

		for item_row in self.get("items"):
			if not item_row.item_code:
				continue
			has_batch_no = frappe.get_cached_value("Item", item_row.item_code, "has_batch_no")
			if has_batch_no and not item_row.batch_no:
				missing_batch_items.append(f"Row #{item_row.idx}: {item_row.item_code}")

		
		if missing_batch_items:
			error_details = "<br>".join(missing_batch_items)
			frappe.throw(
				_("Batch Number is mandatory for the following item(s):<br><br>{0}").format(error_details),
				title=_("Missing Batch Number")
			)

	def set_warehouses_from_delivery_note(self):
		if not self.is_internal_supplier:
			return

		delivery_note = self.get("inter_company_reference")
		
		if not delivery_note:
			return

		dn = frappe.get_doc("Delivery Note", delivery_note)

		# set_from_warehouse will be same as set_target_warehouse of DN
		if dn.set_target_warehouse:
			self.set_from_warehouse = dn.set_target_warehouse
		
		# Get Sales Order to find custom_destination_warehouse
		sales_order = None
		for item in dn.items:
			if item.against_sales_order:
				sales_order = item.against_sales_order
				break
		
		if sales_order:
			so_custom_destination_warehouse = frappe.db.get_value("Sales Order", sales_order, "custom_destination_warehouse")
			if so_custom_destination_warehouse:
				qc_warehouse = frappe.db.get_value("Warehouse", 
					{"parent_warehouse": so_custom_destination_warehouse, "custom_is_qc_warehouse": 1}, 
					"name"
				)
				if qc_warehouse:
					self.set_warehouse = qc_warehouse

				rejected_warehouse = frappe.db.get_value("Warehouse", 
					{"parent_warehouse": so_custom_destination_warehouse, "is_rejected_warehouse": 1}, 
					"name"
				)
				if rejected_warehouse:
					self.rejected_warehouse = rejected_warehouse

				# Cascade to child items
				for item in self.items:
					if qc_warehouse and not item.warehouse:
						item.warehouse = qc_warehouse
					if dn.set_target_warehouse and not item.from_warehouse:
						item.from_warehouse = dn.set_target_warehouse
					if rejected_warehouse and not item.rejected_warehouse:
						item.rejected_warehouse = rejected_warehouse

@frappe.whitelist()
def make_stock_entry(source_name, target_doc=None):
	print("___________________________-----------------------Make stock entry")
	def set_missing_values(source, target):
		target.stock_entry_type = "Material Transfer"
		target.purpose = "Material Transfer"
		target.set_missing_values()
	
	def update_item(source_doc, target_doc, source_parent):
		if source_doc.serial_and_batch_bundle:
			serial_nos = get_serial_nos_from_bundle(source_doc.serial_and_batch_bundle)
			if serial_nos:
				serial_nos = "\n".join(serial_nos)

			batches = get_batches_from_bundle(source_doc.serial_and_batch_bundle)
			if batches:
				if len(batches) == 1:
					target_doc.use_serial_batch_fields = 1
					target_doc.batch_no = next(iter(batches))
				elif not serial_nos:
					cls_obj = SerialBatchCreation(
						{
							"type_of_transaction": "Outward",
							"serial_and_batch_bundle": source_doc.serial_and_batch_bundle,
							"item_code": source_doc.item_code,
							"warehouse": source_doc.warehouse,
						}
					)

					cls_obj.duplicate_package()

					target_doc.serial_and_batch_bundle = cls_obj.serial_and_batch_bundle

			if serial_nos:
				target_doc.use_serial_batch_fields = 1
				target_doc.serial_no = serial_nos

	doclist = get_mapped_doc(
		"Purchase Receipt",
		source_name,
		{
			"Purchase Receipt": {
				"doctype": "Stock Entry",
			},
			"Purchase Receipt Item": {
				"doctype": "Stock Entry Detail",
				"field_map": {
					"warehouse": "s_warehouse",
					"parent": "reference_purchase_receipt",
					"batch_no": "batch_no",
				},
				"postprocess": update_item,
				# This removes the items with qty = 0
				"filter": lambda d: flt(d.qty) == 0,
			},
		},
		target_doc,
		set_missing_values,
	)
	print("doclist -->",doclist)

	return doclist
