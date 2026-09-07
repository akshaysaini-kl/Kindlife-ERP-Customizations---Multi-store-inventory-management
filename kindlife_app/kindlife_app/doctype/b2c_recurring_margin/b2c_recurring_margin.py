# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, get_last_day, today


class B2CRecurringMargin(Document):
	"""
	Stores time-bound customer-facing discount rates per item per supplier.
	Supports multiple entries for the same item to handle intra-month discount changes.
	Submittable — only submitted records are considered by the margin engine.
	"""

	def validate(self):
		self.set_end_date_default()
		self.validate_date_range()
		self.check_overlapping_ranges()
		self.compute_status()

	def before_submit(self):
		self.check_overlapping_ranges(submitted_only=True)
		self.compute_status()

	def on_submit(self):
		"""Retroactively recalculate margins on existing submitted SOs affected by this entry."""
		self.recalculate_affected_sales_orders()

	def recalculate_affected_sales_orders(self):
		"""
		Find all submitted SOs with matching item + supplier whose transaction_date
		falls within this margin's date range, and recalculate their B2C margins.
		"""
		affected_sos = frappe.db.sql("""
			SELECT DISTINCT soi.parent
			FROM `tabSales Order Item` soi
			INNER JOIN `tabSales Order` so ON so.name = soi.parent
			
				AND soi.item_code = %s
				AND soi.supplier = %s
				AND soi.delivered_by_supplier = 1
				AND so.transaction_date BETWEEN %s AND %s
		""", (self.item_code, self.supplier, self.start_date, self.end_date), as_dict=True)
		print("affected_sos", affected_sos)
		if not affected_sos:
			return

		so_names = [row.parent for row in affected_sos]

		frappe.enqueue(
			"kindlife_app.services.margin_engine.recalculate_margins_bulk",
			so_names=so_names,
			brm_name=self.name,
			queue="short",
		)

		frappe.msgprint(
			_("Recalculating B2C margins for {0} affected Sales Order(s) in background.").format(
				len(so_names)
			),
			alert=True,
		)

	def set_end_date_default(self):
		"""Default end_date to last day of current month if left blank."""
		if not self.end_date:
			self.end_date = get_last_day(self.start_date or today())

	def validate_date_range(self):
		"""Ensure start_date <= end_date."""
		if self.start_date and self.end_date:
			if getdate(self.start_date) > getdate(self.end_date):
				frappe.throw(
					_("Start Date ({0}) cannot be after End Date ({1}).").format(
						self.start_date, self.end_date
					)
				)

	def check_overlapping_ranges(self, submitted_only=False):
		"""
		Reject overlapping date ranges for the same Item + Supplier combination.
		An overlap exists if: existing.start_date <= self.end_date AND existing.end_date >= self.start_date
		"""
		filters = {
			"item_code": self.item_code,
			"supplier": self.supplier,
			"name": ["!=", self.name],
		}

		if submitted_only:
			filters["docstatus"] = 1
		else:
			# Check against non-cancelled records (draft + submitted)
			filters["docstatus"] = ["!=", 2]

		overlapping = frappe.db.get_all(
			"B2C Recurring Margin",
			filters=filters,
			fields=["name", "start_date", "end_date", "discount_pct"],
		)

		for entry in overlapping:
			if (
				getdate(entry.start_date) <= getdate(self.end_date)
				and getdate(entry.end_date) >= getdate(self.start_date)
			):
				frappe.throw(
					_(
						"Date range ({0} to {1}) overlaps with existing entry {2} "
						"({3} to {4}) for Item {5} and Supplier {6}."
					).format(
						self.start_date,
						self.end_date,
						frappe.bold(entry.name),
						entry.start_date,
						entry.end_date,
						frappe.bold(self.item_code),
						frappe.bold(self.supplier),
					),
					title=_("Overlapping Date Range"),
				)

	def compute_status(self):
		"""Set status to Active if today falls within the date range, else Inactive."""
		today_date = getdate(today())
		if self.start_date and self.end_date:
			if getdate(self.start_date) <= today_date <= getdate(self.end_date):
				self.status = "Active"
			else:
				self.status = "Inactive"
		else:
			self.status = "Inactive"


@frappe.whitelist()
def get_default_supplier_for_item(item_code):
	"""Return the supplier marked as custom_default_supplier in the Item Supplier table."""
	supplier = frappe.db.get_value(
		"Item Supplier",
		{"parent": item_code, "parenttype": "Item", "custom_default_supplier": 1},
		"supplier",
		order_by="idx asc",
	)
	return supplier or None
