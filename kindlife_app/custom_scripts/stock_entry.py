from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry as OriginalStockEntry
import frappe
from frappe import _
from frappe.utils import cint
from kindlife_app.api.row_locking import RowLockManager, DOCTYPE_LOCK_CONFIG


class StockEntryExtends(OriginalStockEntry):
    def on_submit(self):
        # Validate Match between Item and Batch (Strict Check on Submit)
        self.validate_batch_item_match()
        self.validate_scanning_complete()
        super().on_submit()
        self.update_related_pr()
    
    def on_cancel(self):
        self.update_related_pr()
        super().on_cancel()

    def before_validate(self):
        from .putaway_rule import apply_putaway_rule

        apply_rule = self.apply_putaway_rule and (self.purpose in ["Material Transfer", "Material Receipt"])
        if self.get("items") and apply_rule:
            apply_putaway_rule(self.doctype, self.get("items"), self.company, purpose=self.purpose)
            
        # Validate no duplicate rows for same item/batch/warehouse
        self.validate_duplicate_rows()

    def validate_batch_item_match(self):
        # --- BATCH OWNERSHIP VALIDATOR (STRICT MODE) ---

        mismatches = []

        for item in self.items:
            if item.batch_no:
                # 1. Check who owns the batch
                batch_owner = frappe.db.get_value("Batch", item.batch_no, "item")
                
                # 2. If Owner exists and is NOT the current item -> ERROR
                if batch_owner and batch_owner != item.item_code:
                    
                    # 3. STRICT SEARCH: Look for a batch with the exact same "Custom Batch No"
                    suggestion = "Create New Batch"
                    
                    # We filter by 'custom_batch_no' because that is where we stored the original name
                    candidates = frappe.db.get_all("Batch", 
                        filters={
                            "custom_batch_no": item.batch_no,  # Strict match on the "Name" field
                            "item": item.item_code
                        },
                        pluck="name",
                        limit=1
                    )
                    
                    if candidates:
                        suggestion = f"<b>Use Existing: {candidates[0]}</b>"
                    else:
                        suggestion = f"Create New: {item.batch_no}"
                    
                    # 4. Add to error list
                    mismatches.append({
                        "row": item.idx,
                        "item": item.item_code,
                        "wrong_batch": item.batch_no,
                        "fix": suggestion
                    })

        # --- DISPLAY ERROR ---
        if mismatches:
            # Build HTML Table
            table_rows = ""
            for m in mismatches:
                table_rows += f"""
                <tr>
                    <td style="text-align: center;">{m['row']}</td>
                    <td>{m['item']}</td>
                    <td style="color:red; font-weight:bold;">{m['wrong_batch']}</td>
                    <td>{m['fix']}</td>
                </tr>
                """
            
            msg = f"""
            <p>In the given document, in the following rows, the batch mentioned does not belong to the corresponding item.</p>
            
            <p>In our system, <b>one batch connects to only one item</b>.</p>
            
            <p>If multiple items have the same batch, you need to make a new batch with the same name that connects to the corresponding item.</p>
            
            <p>The table below tells if a batch with the same name exists for the particular item:</p>
            
            <table class="table table-bordered" style="font-size: 12px; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f0f0f0;">
                        <th style="width: 10%;">Row</th>
                        <th style="width: 30%;">Item</th>
                        <th style="width: 30%;">Entered Batch</th>
                        <th style="width: 30%;">Suggestion</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            """
            
            frappe.throw(msg, title="⛔ Batch Mismatch")


    def validate_duplicate_rows(self):
        """
        Validate that there are no multiple rows with same Item Code, Batch No and Source Warehouse.
        This prevents issues with duplicate serial numbers in bundles.
        """
        # Skip duplicate check when putaway rule is applied and SE is linked to a PR
        if getattr(self, "apply_putaway_rule", False) and self.items:
            first_item = self.items[0]
            if getattr(first_item, "reference_purchase_receipt", None):
                return

        row_map = {}
        for row in self.items:
            key = (row.item_code, row.batch_no, row.s_warehouse)
            if key not in row_map:
                row_map[key] = []
            row_map[key].append(row)
            
        for key, rows in row_map.items():
            if len(rows) > 1:
                item_code, batch_no, s_warehouse = key
                frappe.throw(
                    _("Multiple rows found for Item {0}, Batch {1} from Warehouse {2}. Please create separate Stock Entries for these rows to avoid serial number conflicts.").format(
                        frappe.bold(item_code), 
                        frappe.bold(batch_no), 
                        frappe.bold(s_warehouse)
                    )
                )

    def validate_scanning_complete(self):
        """
        Prevent submitting if scanning is not completed for any item row.
        Skipped if custom_skip_barcode_scanning is checked.
        """
        if self.custom_skip_barcode_scanning:
            return

        mismatches = []
        for d in self.items:
            # Skip validation if item is not serialized and has no bundle
            has_serial_no = frappe.db.get_value("Item", d.item_code, "has_serial_no")
            if not has_serial_no and not d.serial_and_batch_bundle:
                continue

            if cint(d.qty) != cint(d.custom_scanned_qty or 0):
                mismatches.append({
                    "row": d.idx,
                    "item_code": d.item_code,
                    "qty": d.qty,
                    "scanned": d.custom_scanned_qty or 0
                })

        if mismatches:
            table_rows = ""
            for m in mismatches:
                table_rows += f"<tr><td>{m['row']}</td><td>{m['item_code']}</td><td>{m['qty']}</td><td>{m['scanned']}</td></tr>"

            msg = f"""
            <p>Scanning is not completed for the following items. Please scan all serial numbers before submitting.</p>
            <table class="table table-bordered" style="font-size: 12px; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f0f0f0;">
                        <th>Row</th>
                        <th>Item</th>
                        <th>Required Qty</th>
                        <th>Scanned Qty</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            """
            frappe.throw(msg, title=_("Scanning Not Complete"))

    def update_related_pr(self):

            # Get details of all rows in the Stock Entry
            rows = frappe.db.get_all("Stock Entry Detail",
                filters ={"parent": self.name},
                fields=[
                    "reference_purchase_receipt"  
                ]
            )			


            # In our flow, we will make only one SE per PR, so we can check any of the items for the connected PR
            if not rows[0].reference_purchase_receipt:
                return
            else:
                pur_rec = rows[0].reference_purchase_receipt

            if self.docstatus == 1:
                # Fetch link to connected PR
                pr = frappe.get_doc("Purchase Receipt", pur_rec)

                # Update the workflow status of PR
                if pr:
                    frappe.db.set_value("Purchase Receipt", pr.name, "workflow_state", "Completed")


            if self.docstatus == 2:
                pr_doc = frappe.get_doc("Purchase Receipt", pur_rec)			
                # Update the workflow status of PR
                if pr_doc:
                    frappe.db.set_value("Purchase Receipt", pr_doc.name, "workflow_state", "Pending Putaway")


@frappe.whitelist()
def get_bundle_serial_data(stock_entry_name):
    """
    Fetches all serial and batch entries for all bundles linked to a Stock Entry.
    Returns: {bundle_name: [{'serial_no': '...', 'batch_no': '...'}, ...]}
    """
    if not stock_entry_name:
        return {}

    # Get all bundles linked to this Stock Entry
    bundles = frappe.get_all(
        "Serial and Batch Bundle",
        filters={"voucher_no": stock_entry_name, "is_cancelled": 0},
        fields=["name"]
    )

    if not bundles:
        return {}

    bundle_names = [b.name for b in bundles]
    
    # Get all entries for these bundles
    entries = frappe.get_all(
        "Serial and Batch Entry",
        filters={"parent": ["in", bundle_names]},
        fields=["parent", "serial_no", "batch_no"]
    )

    result = {}
    for entry in entries:
        if entry.parent not in result:
            result[entry.parent] = []
        result[entry.parent].append({
            "serial_no": entry.serial_no,
            "batch_no": entry.batch_no
        })

    return result




def before_save(doc, method):
    """
    Hook that runs before Stock Entry is saved.
    Automatically merges scanned data if document was modified by another user.
    """
    # Skip for new documents
    if doc.is_new():
        return
    
    # Skip if explicitly disabled
    if doc.flags.skip_smart_merge:
        return
    
    # Get latest version from database
    try:
        latest = frappe.db.get_value(
            doc.doctype,
            doc.name,
            ['modified', 'modified_by'],
            as_dict=True
        )
    except:
        return
    
    # Check if document was modified by someone else
    if latest and str(latest.modified) != str(doc.modified):
        # Get configuration
        config = DOCTYPE_LOCK_CONFIG.get("Stock Entry")
        if not config:
            return
        
        # Create manager with field names
        manager = RowLockManager(
            key_prefix=config["key_prefix"],
            doctype="Stock Entry",
            child_table=config["child_table"],
            scanned_serial_field=config["scanned_serial_field"],
            scanned_qty_field=config["scanned_qty_field"]
        )
        
       
        # Transfer cleared rows from frontend to backend flags
        if hasattr(doc, '__cleared_rows'):
            doc.flags.cleared_rows = doc.__cleared_rows
        
        # Perform smart merge
        merge_stats = manager.smart_merge_scanned_data(doc)

        
        # Show notification if merge happened
        if merge_stats.get("merged"):
            frappe.msgprint(
                f"Document was modified by {latest.modified_by}. "
                f"Merged {merge_stats['rows_merged']} row(s) with {merge_stats['serials_added']} additional serials.",
                indicator='blue',
                alert=True
            )

