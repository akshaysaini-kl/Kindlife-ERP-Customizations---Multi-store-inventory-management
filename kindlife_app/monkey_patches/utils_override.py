import frappe
from frappe import _
from erpnext.buying.utils import set_stock_levels,validate_item_and_get_basic_data,validate_stock_item_warehouse,validate_end_of_life,cstr,cint


def validate_for_items(doc) -> None:
	items = []
	for d in doc.get("items"):
		print("###################@@@@@@@@@@@@@@@@@@@@@@@@@@##########################")
		# if not d.qty:
		# 	if doc.doctype == "Purchase Receipt" and d.rejected_qty:
		# 		continue
		# 	frappe.throw(_("Please enter quantity for Item {0}").format(d.item_code))

		set_stock_levels(row=d)  # update with latest quantities
		item = validate_item_and_get_basic_data(row=d)
		validate_stock_item_warehouse(row=d, item=item)
		validate_end_of_life(d.item_code, item.end_of_life, item.disabled)

		items.append(cstr(d.item_code))

	if (
		items
		and len(items) != len(set(items))
		and not cint(frappe.db.get_single_value("Buying Settings", "allow_multiple_items") or 0)
	):
		frappe.throw(_("Same item cannot be entered multiple times."))

