# Copyright (c) 2026, Auriga IT and Contributors
# See license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate, flt


class ItemMRP(Document):

    def validate(self):
        self._populate_old_mrp()
        self._validate_new_mrp()
        self._validate_effective_from()

    def before_submit(self):
        """Capture old MRP from Item just before submission."""
        self._populate_old_mrp()

    def on_submit(self):
        """If effective_from is today or in the past, apply immediately."""
        if getdate(self.effective_from) <= getdate(today()):
            apply_mrp(self)

    def on_cancel(self):
        """If the document was already applied, revert the Item's MRP."""
        if self.status == "Applied":
            item_doc = frappe.get_doc("Item", self.item_code)
            item_doc.db_set("custom_mrp", self.old_mrp)
            
            # Sync reverted price to CS-Cart
            try:
                from kindlife_app.kindlife_app.custom_scripts.item import update_cs_cart
                update_cs_cart(item_doc)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"CS-Cart Sync Error for Item {self.item_code} on MRP Cancel")
                
            frappe.msgprint(frappe._("Item MRP reverted to {0}. Standard Item Prices must be manually updated if expired.").format(self.old_mrp))

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _validate_new_mrp(self):
        if not self.new_mrp or flt(self.new_mrp) <= 0:
            frappe.throw(frappe._("New MRP must be greater than zero."))
            
        if flt(self.new_mrp) == flt(self.old_mrp):
            frappe.throw(frappe._("New MRP ({0}) is the same as the current MRP. No change needed.").format(self.old_mrp))

    def _validate_effective_from(self):
        if not self.effective_from:
            frappe.throw(frappe._("Effective From date is mandatory."))

        # Prevent overlapping/duplicate effective dates for the same item
        existing_mrp = frappe.db.get_value(
            "Item MRP",
            {
                "item_code": self.item_code,
                "effective_from": self.effective_from,
                "docstatus": ["!=", 2],
                "name": ["!=", self.name or ""]
            },
            "name"
        )
        if existing_mrp:
            frappe.throw(
                frappe._("An MRP change ({0}) is already scheduled for this item on {1}.").format(
                    existing_mrp, frappe.utils.formatdate(self.effective_from)
                )
            )

    def _populate_old_mrp(self):
        current_mrp = frappe.db.get_value("Item", self.item_code, "custom_mrp")
        self.old_mrp = current_mrp or 0


# ------------------------------------------------------------------ #
# Utility: apply a single Item MRP document                            #
# ------------------------------------------------------------------ #

def apply_mrp(doc):
    """
    Apply the MRP change from an Item MRP document:
    1. Update custom_mrp on Item
    2. Sync updated Item to CS-Cart
    3. Expire old-MRP Item Prices
    4. Mark Item MRP status as Applied
    """
    item_doc = frappe.get_doc("Item", doc.item_code)
    item_doc.db_set("custom_mrp", doc.new_mrp)
    
    # Sync to CS-Cart
    try:
        from kindlife_app.kindlife_app.custom_scripts.item import update_cs_cart
        update_cs_cart(item_doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"CS-Cart Sync Error for Item {doc.item_code} on MRP Apply")

    expire_old_mrp_item_prices(
        item_code=doc.item_code,
        old_mrp=doc.old_mrp,
        effective_from=doc.effective_from,
    )

    frappe.db.set_value("Item MRP", doc.name, "status", "Applied")
    frappe.db.commit()

    frappe.msgprint(
        frappe._("MRP updated to {0} for item {1}").format(doc.new_mrp, doc.item_code),
        alert=True,
    )


# ------------------------------------------------------------------ #
# Utility: expire Item Prices carrying old MRP                         #
# ------------------------------------------------------------------ #

def expire_old_mrp_item_prices(item_code, old_mrp, effective_from):
    """
    Set valid_upto = effective_from - 1 day on all Item Price records where:
      - item_code matches
      - custom_buying_price (MRP field on Item Price) matches old_mrp
      - valid_upto is NULL or >= effective_from (still active)
    """
    if not old_mrp:
        return

    from frappe.utils import add_days

    expiry_date = add_days(effective_from, -1)

    item_prices = frappe.get_all(
        "Item Price",
        filters={
            "item_code": item_code,
            "custom_buying_price": old_mrp,
        },
        fields=["name", "valid_upto"],
    )

    for ip in item_prices:
        # Only expire if not already expired before the new effective date
        if not ip.valid_upto or getdate(ip.valid_upto) >= getdate(effective_from):
            frappe.db.set_value("Item Price", ip.name, "valid_upto", expiry_date)


# ------------------------------------------------------------------ #
# Scheduled task: apply all pending MRP changes                        #
# ------------------------------------------------------------------ #

def apply_pending_mrp():
    """
    Daily cron: find all submitted Item MRP docs that are Pending
    and whose effective_from <= today, then apply them.
    """
    pending_docs = frappe.get_all(
        "Item MRP",
        filters={
            "docstatus": 1,           # submitted
            "status": "Pending",
            "effective_from": ["<=", today()],
        },
        fields=["name", "item_code", "new_mrp", "old_mrp", "effective_from"],
    )

    for d in pending_docs:
        try:
            doc = frappe.get_doc("Item MRP", d.name)
            apply_mrp(doc)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Item MRP Apply Error: {d.name}",
            )
