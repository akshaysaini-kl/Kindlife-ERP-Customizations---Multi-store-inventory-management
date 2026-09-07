import frappe
from frappe import _

@frappe.whitelist()
def get_all_serials_for_stock_entry(stock_entry_name):
    """
    Get all serial numbers for all items in a stock entry using the linked Serial and Batch Bundle.
    """
    try:
        stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
        all_serials = []
        
        for item in stock_entry.items:
            # Skip if no bundle is linked to this specific row
            if not item.serial_and_batch_bundle:
                continue
            
            # DIRECT FIX: Fetch entries specifically from the bundle linked to this row.
            # We do not query by Item Code or Transaction Type, avoiding confusion 
            # when multiple rows have the same item.
            bundle_entries = frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": item.serial_and_batch_bundle},
                fields=["serial_no", "qty", "batch_no", "warehouse"]
            )
            
            # Get barcode for each serial
            for entry in bundle_entries:
                # Construct barcode value
                barcode_value = f"{entry.warehouse} - {entry.serial_no}"
                
                serial_data = {
                    "serial_no": entry.serial_no,
                    "item_code": item.item_code,
                    "item_idx": item.idx, # This ensures the serial belongs to the specific row index
                    "barcode": barcode_value,
                    "batch_no": entry.batch_no
                }
                
                all_serials.append(serial_data)

        return all_serials
        
    except Exception as e:
        frappe.log_error(f"Error getting all serials for stock entry: {str(e)}")
        return []