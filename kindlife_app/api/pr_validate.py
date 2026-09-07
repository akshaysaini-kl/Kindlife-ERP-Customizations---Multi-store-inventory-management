import frappe
from frappe.utils import flt
from frappe import _
import json


# This method checks that for each item in PR, the sum of accepted and rejected qty equals custom received qty
# This will not be applied for Purchase returns
@frappe.whitelist()
def verify_pr_sum(doc):
	if isinstance(doc, str):
		doc = json.loads(doc)

	if doc.get("is_return"):
		return True

	for item_row in doc.get("items", []):
		accepted_qty = flt(item_row.get("qty"))
		rejected_qty = flt(item_row.get("rejected_qty"))
		custom_received = flt(item_row.get("custom_received"))
		calculated_sum = accepted_qty + rejected_qty    

		if flt(calculated_sum) != flt(custom_received):
			frappe.throw(
				_("Row #{idx}: The sum of Accepted Qty ({accepted}) and Rejected Qty ({rejected}) must be equal to the Custom Received Qty ({custom}).").format(
					idx=item_row.get("idx"),
					accepted=accepted_qty,
					rejected=rejected_qty,
					custom=custom_received,
				),
				title=_("Quantity Mismatch")
			)
			return False
	return True

			

def verify_received_is_non_zero(doc,method):
	for item_row in doc.get("items"):

		custom_received = flt(item_row.custom_received)

		if custom_received == 0:
			frappe.throw(
				_("Row #{idx}: Received can not be 0").format(
					idx=item_row.idx,
				),
				title=_("Quantity Mismatch")
			)
