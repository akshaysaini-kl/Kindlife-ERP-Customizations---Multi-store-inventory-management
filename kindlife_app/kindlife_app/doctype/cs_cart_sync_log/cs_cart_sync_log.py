# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class CSCartSyncLog(Document):
    @frappe.whitelist()
    def retry_sync(self):
        """
        Retry the inventory sync for this log entry.
        """
        # Import here to avoid circular import issues
        from kindlife_app.custom_scripts.inventory_sync import sync_inventory_to_cscart
        
        # Enqueue the sync job again
        frappe.enqueue(
            method="kindlife_app.custom_scripts.inventory_sync.sync_inventory_to_cscart",
            queue="default",
            timeout=300,
            is_async=True,
            job_name=f"cs_cart_inventory_sync_retry_{self.name}",
            item_code=self.item_code,
            log_name=self.name, # Pass self.name to update this log instead of creating new
            enqueue_after_commit=True
        )
        
        # Update status to Processing
        self.status = "Queued"
        self.message = "Retry enqueued..."
        self.retry_count = (self.retry_count or 0) + 1
        self.last_retry = frappe.utils.now_datetime()
        self.save()
        
        msg = f"Retry enqueued for {self.item_code}"
        frappe.msgprint(msg)
        return msg
