# Copyright (c) 2026, Auriga IT and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today, add_days, get_last_day, getdate


class TestB2CRecurringMargin(FrappeTestCase):
	"""Tests for B2C Recurring Margin doctype."""

	def setUp(self):
		# Clean up any test records
		frappe.db.delete("B2C Recurring Margin", {"item_code": "_Test Item"})
		frappe.db.commit()

	def test_end_date_auto_default(self):
		"""End Date should default to last day of current month if left blank."""
		doc = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 10,
			"start_date": today(),
		})
		doc.validate()
		self.assertEqual(getdate(doc.end_date), getdate(get_last_day(today())))

	def test_start_after_end_rejected(self):
		"""Should throw if start_date > end_date."""
		doc = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 10,
			"start_date": add_days(today(), 10),
			"end_date": today(),
		})
		self.assertRaises(frappe.ValidationError, doc.validate)

	def test_overlapping_ranges_rejected(self):
		"""Should reject overlapping date ranges for same Item + Supplier."""
		doc1 = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 10,
			"start_date": today(),
			"end_date": add_days(today(), 15),
		})
		doc1.insert()

		doc2 = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 15,
			"start_date": add_days(today(), 10),
			"end_date": add_days(today(), 25),
		})
		self.assertRaises(frappe.ValidationError, doc2.insert)

	def test_non_overlapping_ranges_accepted(self):
		"""Should accept non-overlapping date ranges for same Item + Supplier."""
		doc1 = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 10,
			"start_date": today(),
			"end_date": add_days(today(), 10),
		})
		doc1.insert()

		doc2 = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 15,
			"start_date": add_days(today(), 11),
			"end_date": add_days(today(), 25),
		})
		doc2.insert()
		self.assertTrue(doc2.name)

	def test_status_computation(self):
		"""Status should be Active if today is within the date range."""
		doc = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 10,
			"start_date": add_days(today(), -5),
			"end_date": add_days(today(), 5),
		})
		doc.validate()
		self.assertEqual(doc.status, "Active")

		# Future entry
		doc2 = frappe.get_doc({
			"doctype": "B2C Recurring Margin",
			"item_code": "_Test Item",
			"supplier": "_Test Supplier",
			"discount_pct": 10,
			"start_date": add_days(today(), 30),
			"end_date": add_days(today(), 60),
		})
		doc2.validate()
		self.assertEqual(doc2.status, "Inactive")
