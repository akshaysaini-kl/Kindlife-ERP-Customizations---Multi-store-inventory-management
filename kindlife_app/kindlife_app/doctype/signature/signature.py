# Copyright (c) 2025, Auriga IT and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe

class Signature(Document):
	def before_insert(self):
		self.user = frappe.session.user
