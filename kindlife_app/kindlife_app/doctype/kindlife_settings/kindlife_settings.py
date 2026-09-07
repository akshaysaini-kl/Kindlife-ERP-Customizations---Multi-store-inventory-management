# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class KindlifeSettings(Document):
	"""
	Single DocType for configuring duplicate detection behavior.
	
	This doctype allows administrators to:
	- Enable/disable duplicate detection per doctype
	- Configure similarity threshold
	- Set custom warning message templates
	- Control data import behavior
	"""
	
	def validate(self):
		"""Validate settings before saving."""
		# Ensure threshold is within valid range
		if self.similarity_threshold:
			if self.similarity_threshold < 0 or self.similarity_threshold > 100:
				frappe.throw("Similarity threshold must be between 0 and 100")
	
	def on_update(self):
		"""Clear cache when settings are updated."""
		# Clear all duplicate detection caches
		from kindlife_app.utils.duplicate_detector import clear_duplicate_detection_cache
		
		doctypes_fields = {
			"Item Group": "item_group_name",
			"Customer Group": "customer_group_name",
			"Customer": "customer_name",
			"Brand": "brand"
		}
		
		for doctype, field in doctypes_fields.items():
			clear_duplicate_detection_cache(doctype, field)
		
		frappe.msgprint("Duplicate detection cache cleared successfully", alert=True)
