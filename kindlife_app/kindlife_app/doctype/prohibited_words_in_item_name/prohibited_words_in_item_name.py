# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

import frappe
import re
from frappe import _
from frappe.model.document import Document

class ProhibitedWordsinItemName(Document):
	def validate(self):
		self.validate_prohibited_words()

	def validate_prohibited_words(self):
		if not self.prohibited_words:
			return
		
		seen_words = set()
		for row in self.prohibited_words:
			if not row.word:
				continue

			# 1. Format Check (Alphanumeric only)
			if not re.match(r"^[a-zA-Z0-9]+$", row.word):
				frappe.throw(
					_("Row #{0}: A Prohibited word '{1}' cannot contain special character or spaces.<br> Please add individual words (e.g., 'Super' and 'Sale' separately instead of 'Super-Sale').").format(
						row.idx, row.word
					)
				)

			# 2. Duplicate Check (Case-insensitive)
			word_lower = row.word.lower().strip()
			if word_lower in seen_words:
				frappe.throw(
					_("Row #{0}: The word '{1}' is already present in the list.").format(
						row.idx, row.word
					)
				)
			seen_words.add(word_lower)

	def on_update(self):
		frappe.cache().delete_key("prohibited_words_list")

	def on_trash(self):
		frappe.cache().delete_key("prohibited_words_list")
