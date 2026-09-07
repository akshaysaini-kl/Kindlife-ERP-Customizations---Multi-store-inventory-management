import frappe
from frappe import _

@frappe.whitelist()
def get_available_serials_for_batches(batches, pick_list_items):
    """
    Get available serial numbers for given batches
    Args:
        batches: List of batch numbers
        pick_list_items: Pick list items with item_code, warehouse, batch_no info
    Returns:
        List of dictionaries with serial_no, batch_no, item_code, warehouse
    """
    try:
        if isinstance(batches, str):
            import json
            batches = json.loads(batches)
        
        if isinstance(pick_list_items, str):
            import json
            pick_list_items = json.loads(pick_list_items)
        
        if not batches:
            return []
        
        # Create a set of unique (item_code, warehouse, batch_no) combinations
        unique_combinations = set()
        for item in pick_list_items:
            if item.get('batch_no') and item.get('item_code') and item.get('warehouse'):
                unique_combinations.add((item['item_code'], item['warehouse'], item['batch_no']))
        
        available_serials = []
        
        for item_code, warehouse, batch_no in unique_combinations:
            # Query to get available serial numbers for this specific combination
            serials = frappe.db.sql("""
                SELECT 
                    sn.name as serial_no,
                    sn.custom_barcode,
                    sn.batch_no,
                    sn.item_code,
                    sn.warehouse,
                    sn.status
                FROM `tabSerial No` sn
                WHERE sn.batch_no = %(batch_no)s
                    AND sn.item_code = %(item_code)s
                    AND sn.warehouse = %(warehouse)s
                    AND sn.status = 'Active'
                    AND sn.docstatus < 2
                    AND sn.custom_barcode IS NOT NULL
                    AND sn.custom_barcode != ''
                ORDER BY sn.creation ASC
            """, {
                'batch_no': batch_no,
                'item_code': item_code,
                'warehouse': warehouse
            }, as_dict=True)
            
            available_serials.extend(serials)
            
        return available_serials
        
    except Exception as e:
        frappe.log_error(f"Error in get_available_serials_for_batches: {str(e)}")
        frappe.throw(_("Error fetching available serials: {0}").format(str(e)))

@frappe.whitelist()
def validate_serial_batch_compatibility(serial_no, expected_batch, item_code, warehouse):
    """
    Validate if a serial number belongs to the expected batch for given item and warehouse
    """
    try:
        serial_doc = frappe.get_doc("Serial No", serial_no)
        
        if serial_doc.batch_no != expected_batch:
            return {
                'valid': False,
                'message': f"Serial {serial_no} belongs to batch {serial_doc.batch_no}, expected {expected_batch}"
            }
            
        if serial_doc.item_code != item_code:
            return {
                'valid': False,
                'message': f"Serial {serial_no} is for item {serial_doc.item_code}, expected {item_code}"
            }
            
        if serial_doc.warehouse != warehouse:
            return {
                'valid': False,
                'message': f"Serial {serial_no} is in warehouse {serial_doc.warehouse}, expected {warehouse}"
            }
            
        if serial_doc.status != 'Active':
            return {
                'valid': False,
                'message': f"Serial {serial_no} is not active (status: {serial_doc.status})"
            }
            
        return {
            'valid': True,
            'message': 'Serial number is valid for the expected batch'
        }
        
    except frappe.DoesNotExistError:
        return {
            'valid': False,
            'message': f"Serial number {serial_no} does not exist"
        }
    except Exception as e:
        frappe.log_error(f"Error validating serial {serial_no}: {str(e)}")
        return {
            'valid': False,
            'message': f"Error validating serial: {str(e)}"
        }