import frappe
from erpnext.stock.serial_batch_bundle import SerialBatchBundle
from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import StockLedgerEntry as originalStockLedgerEntry


class StockLedgerEntryExtends(originalStockLedgerEntry):
	def on_submit(self):
		print("Overriden stock ;ledger entry")
		self.check_stock_frozen_date()

		# Added to handle few test cases where serial_and_batch_bundles are not required
		if frappe.flags.in_test and frappe.flags.ignore_serial_batch_bundle_validation:
			return

		if self.is_adjustment_entry:
			return
		# print("#@@@@@@@@@@@@@@@@@@@@##############@@@@@@@@@@@@@@@@@@@--->",self.voucher_type)
		if self.voucher_type == "Purchase Receipt":
			pass
		else:
			if not self.get("via_landed_cost_voucher"):
				SerialBatchBundle(
					sle=self,
					item_code=self.item_code,
					warehouse=self.warehouse,
					company=self.company,
				)

			self.validate_serial_batch_no_bundle()
