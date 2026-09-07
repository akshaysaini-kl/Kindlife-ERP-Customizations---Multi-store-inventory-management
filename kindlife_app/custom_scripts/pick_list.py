import frappe
from erpnext.stock.doctype.pick_list.pick_list import PickList
from frappe import _
from kindlife_app.utils.shipment_utils import sync_shipment_docs_for_doc
from frappe.utils import flt
from kindlife_app.api.row_locking import RowLockManager, DOCTYPE_LOCK_CONFIG



class PickListExtends(PickList):
    def before_save(self):
        self.update_status()
        if not self.custom_manually_picking:
            self.set_item_locations()

        if self.get("locations"):
            self.validate_sales_order_percentage()

        sync_shipment_docs_for_doc(self, "sales_order", "locations")
        # Compute scanning percent from picked_qty vs qty
        self.update_scanning_percent()

    def update_scanning_percent(self):
        """Calculate and store scanning completion percentage"""
        total_qty = sum(flt(item.qty) for item in self.get("locations", []))
        total_picked = sum(flt(item.picked_qty) for item in self.get("locations", []))
        self.custom_scanning_percent = flt(
            (total_picked / total_qty * 100) if total_qty else 0, 1
        )


def warn_multiple_sales_orders_on_submit(doc, method):
    """Throw a warning if locations are linked to more than one Sales Order"""
    so_to_rows = {}
    for item in doc.locations:
        if not item.sales_order:
            continue
        so_to_rows.setdefault(item.sales_order, []).append(item.idx)

    if len(so_to_rows) <= 1:
        return

    lines = []
    for i, (so, idxs) in enumerate(so_to_rows.items(), start=1):
        row_list = "".join(f"<li>{idx}</li>" for idx in idxs)
        lines.append(f"<li><b>{i}. {so}</b><ul>{row_list}</ul></li>")

    frappe.throw(
        msg=f"<p>This Pick List is linked to <b>{len(so_to_rows)} Sales Orders</b>. Please verify before submitting.</p><ul>{''.join(lines)}</ul>",
        title=_("Multiple Sales Orders Detected")
    )


def validate_batch_numbers_on_submit(doc, method):
    """Validate that all items in locations child table have batch_no value"""
    missing_items = []

    # Iterate through all items to find missing batch numbers
    for item in doc.locations:
        if not item.batch_no:
            missing_items.append({
                "idx": item.idx,
                "item_code": item.item_code
            })

    # If there are missing items, construct the table and throw the error
    if missing_items:
        table_html = """
            <table class="table table-bordered table-condensed">
                <thead>
                    <tr>
                        <th>Row #</th>
                        <th>Item Code</th>
                    </tr>
                </thead>
                <tbody>
        """

        for row in missing_items:
            table_html += f"""
                <tr>
                    <td>{row['idx']}</td>
                    <td>{row['item_code']}</td>
                </tr>
            """

        table_html += "</tbody></table>"

        frappe.throw(
            msg=f"<b>The following items are missing Batch Numbers:</b><br><br>{table_html}",
            title=_("Missing Batch Numbers")
        )



def before_save(doc, method):
    """
    Hook that runs before Pick List is saved.
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
        config = DOCTYPE_LOCK_CONFIG.get("Pick List")
        if not config:
            return
        
        # Create manager with field names
        manager = RowLockManager(
            key_prefix=config["key_prefix"],
            doctype="Pick List",
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
