import frappe
from frappe import _
from erpnext.controllers.accounts_controller import InvalidQtyError
from frappe.utils import flt
from erpnext.controllers.accounts_controller import AccountsController as OriginalAccountsController

class AccountsController(OriginalAccountsController):
	def validate_qty_is_not_zero(self):
		print("Inside Override validate_qty_is_not_zero")
		if self.flags.allow_zero_qty:
			return

		if self.doctype == "Purchase Receipt":
			return


		for item in self.items:
			if self.doctype == "Purchase Receipt" and item.rejected_qty:
				continue

			if not flt(item.qty):
				frappe.throw(
					msg=_("Row #{0}: Quantity for Item {1} cannot be zero.").format(
						item.idx, frappe.bold(item.item_code)
					),
					title=_("Invalid Quantity"),
					exc=InvalidQtyError,
				)
