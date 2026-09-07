import frappe
from erpnext.controllers.stock_controller import StockController
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	get_type_of_transaction,
)


class overrideStockController(StockController):
	def validate_inspection(self):
		pass
		"""Checks if quality inspection is set/ is valid for Items that require inspection."""
		# inspection_fieldname_map = {
		# 	"Purchase Receipt": "inspection_required_before_purchase",
		# 	"Purchase Invoice": "inspection_required_before_purchase",
		# 	"Subcontracting Receipt": "inspection_required_before_purchase",
		# 	"Sales Invoice": "inspection_required_before_delivery",
		# 	"Delivery Note": "inspection_required_before_delivery",
		# }
		# inspection_required_fieldname = inspection_fieldname_map.get(self.doctype)
		# # return if inspection is not required on document level
		# if (
		# 	(not inspection_required_fieldname and self.doctype != "Stock Entry")
		# 	or (self.doctype == "Stock Entry" and not self.inspection_required)
		# 	or (self.doctype in ["Sales Invoice", "Purchase Invoice"] and not self.update_stock)
		# ):
		# 	return
		# for row in self.get("items"):
		# 	qi_required = False
		# 	if inspection_required_fieldname and frappe.db.get_value(
		# 		"Item", row.item_code, inspection_required_fieldname
		# 	):
		# 		qi_required = True
		# 	elif self.doctype == "Stock Entry" and row.t_warehouse:
		# 		qi_required = True  # inward stock needs inspection
		# 	if row.get("is_scrap_item"):
		# 		continue
		# 	if qi_required:  # validate row only if inspection is required on item level
		# 		self.validate_qi_presence(row)
		# 		if self.docstatus == 1:
		# 			pass
		# 			self.validate_qi_submission(row)
		# 			self.validate_qi_rejection(row)




	def update_bundle_details(self, bundle_details, table_name, row, is_rejected=False, parent_details=None):
		print("Inside the monkey patched update_bundle_details function _________________++++++++++++++++++++++++==========================")
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

		# Since qty field is different for different doctypes
		qty = row.get("qty")
		warehouse = row.get("warehouse")

		if table_name == "packed_items":
			type_of_transaction = "Inward"
			if not self.is_return:
				type_of_transaction = "Outward"
		elif table_name == "supplied_items":
			qty = row.consumed_qty
			warehouse = self.supplier_warehouse
			type_of_transaction = "Outward"
			if self.is_return:
				type_of_transaction = "Inward"
		else:
			type_of_transaction = get_type_of_transaction(self, row)

		if hasattr(row, "stock_qty"):
			qty = row.stock_qty

		
		# If the SE is connected to PR, make sure the serial no has the target warehouse.
		if self.doctype == "Stock Entry" :
			if not row.reference_purchase_receipt:
				qty = row.transfer_qty
				warehouse = row.s_warehouse or row.t_warehouse
			else:
				qty = row.transfer_qty
				warehouse = row.t_warehouse

		serial_nos = row.serial_no
		if is_rejected:
			serial_nos = row.get("rejected_serial_no")
			type_of_transaction = "Inward" if not self.is_return else "Outward"
			qty = row.get("rejected_qty")
			warehouse = row.get("rejected_warehouse")

		if (
			self.is_internal_transfer()
			and self.doctype in ["Sales Invoice", "Delivery Note"]
			and self.is_return
		):
			warehouse = row.get("target_warehouse") or row.get("warehouse")
			type_of_transaction = "Outward"

		if table_name == "packed_items":
			if not warehouse:
				warehouse = parent_details[row.parent_detail_docname].warehouse
			bundle_details["voucher_detail_no"] = parent_details[row.parent_detail_docname].name
		print("@@@@@@@@@@@@##########@@@@@@",warehouse)
		bundle_details.update(
			{
				"qty": qty,
				"is_rejected": is_rejected,
				"type_of_transaction": type_of_transaction,
				"warehouse": warehouse,
				"batches": frappe._dict({row.batch_no: qty}) if row.batch_no else None,
				"serial_nos": get_serial_nos(serial_nos) if serial_nos else None,
				"batch_no": row.batch_no,
			}
		)


	def make_bundle_using_old_serial_batch_fields(self, table_name=None, via_landed_cost_voucher=False):
		if self.get("_action") == "update_after_submit":
			return

		# To handle test cases
		if frappe.flags.in_test and frappe.flags.use_serial_and_batch_fields:
			return

		if not table_name:
			table_name = "items"

		if self.doctype == "Asset Capitalization":
			table_name = "stock_items"

		parent_details = frappe._dict()
		if table_name == "packed_items":
			parent_details = self.get_parent_details_for_packed_items()

		for row in self.get(table_name):
			if (
				not via_landed_cost_voucher
				and row.serial_and_batch_bundle
				and (row.serial_no or row.batch_no)
			):
				self.validate_serial_nos_and_batches_with_bundle(row)

			if not row.serial_no and not row.batch_no and not row.get("rejected_serial_no"):
				continue

			if not row.use_serial_batch_fields and (
				row.serial_no or row.batch_no or row.get("rejected_serial_no")
			):
				row.use_serial_batch_fields = 1

			if row.use_serial_batch_fields and (
				not row.serial_and_batch_bundle and not row.get("rejected_serial_and_batch_bundle")
			):
				print("rate 1",row.get("rate"))
				print("rate 1",row.get("valuation_rate"))
				bundle_details = {
					"item_code": row.get("rm_item_code") or row.item_code,
					"posting_date": self.posting_date,
					"posting_time": self.posting_time,
					"voucher_type": self.doctype,
					"voucher_no": self.name,
					"voucher_detail_no": row.name,
					"company": self.company,
					"is_rejected": 1 if row.get("rejected_warehouse") else 0,
					"use_serial_batch_fields": row.use_serial_batch_fields,
					"via_landed_cost_voucher": via_landed_cost_voucher,
					"do_not_submit": True if not via_landed_cost_voucher else False,
					"incoming_rate":row.get("rate") or row.get("valuation_rate") or row.get("incoming_rate") or 0
				}

				if row.get("qty") or row.get("consumed_qty") or row.get("stock_qty"):
					self.update_bundle_details(bundle_details, table_name, row, parent_details=parent_details)
					self.create_serial_batch_bundle(bundle_details, row)

				if row.get("rejected_qty"):
					self.update_bundle_details(bundle_details, table_name, row, is_rejected=True)
					self.create_serial_batch_bundle(bundle_details, row)



