# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

"""
Data Import Hooks for Duplicate Detection

This module provides hooks for the data import workflow to detect and warn
about potential duplicates during bulk imports.
"""

import frappe
from frappe import _
from kindlife_app.utils.duplicate_detector import batch_check_duplicates, get_configured_threshold, is_duplicate_detection_enabled
from typing import Dict, List


def validate_data_import_duplicates(data_import, method=None):
    """
    Validate data import for potential duplicates before processing.
    
    This hook is called during the data import process to check all rows
    for potential duplicates and add warnings to the import log.
    Duplicates will be saved in disabled state for manual review.
    
    Args:
        data_import: The Data Import document
        method: The method name (before_import, etc.)
    """
    # Check if this is a supported doctype
    doctype = data_import.reference_doctype
    
    if doctype not in ["Item Group", "Customer Group", "Brand", "Supplier Group"]:
        return
    
    # Check if duplicate detection is enabled
    if not is_duplicate_detection_enabled(doctype):
        return
    
    # Get the name field for this doctype
    name_field_map = {
        "Item Group": "item_group_name",
        "Customer Group": "customer_group_name",
        "Brand": "brand",
        "Supplier Group": "supplier_group_name"
    }
    
    name_field = name_field_map.get(doctype)
    if not name_field:
        return
    
    # Get threshold
    threshold = get_configured_threshold() or 80
    
    # Extract values from import data
    try:
        import_file = data_import.get_importer()
        if not import_file:
            return
        
        # Get all values to check
        values_to_check = []
        for payload in import_file.get_payloads_for_import():
            doc_data = payload.get("doc", {})
            value = doc_data.get(name_field)
            if value:
                values_to_check.append(value)
        
        if not values_to_check:
            return
        
        # Batch check for duplicates
        duplicate_results = batch_check_duplicates(
            doctype=doctype,
            name_field=name_field,
            values=values_to_check,
            threshold=threshold
        )
        
        # Show detailed warnings for duplicates found
        if duplicate_results:
            warning_count = len(duplicate_results)
            
            # Build detailed warning message
            warning_msg = f"<b>Found {warning_count} potential duplicate(s) in the import data:</b><br><br>"
            
            for idx, (value, similar_records) in enumerate(duplicate_results.items(), 1):
                warning_msg += f"{idx}. <b>{value}</b> is similar to:<br>"
                for record in similar_records[:3]:  # Show top 3 matches
                    warning_msg += f"&nbsp;&nbsp;&nbsp;• {record['field_value']} ({record['similarity']}% match) - "
                    warning_msg += f"<a href='/app/{doctype.lower().replace(' ', '-')}/{record['name']}'>{record['name']}</a><br>"
                warning_msg += "<br>"
            
            warning_msg += "<br><b>⚠️ These records will be saved in DISABLED state for manual review.</b>"
            
            frappe.msgprint(
                msg=warning_msg,
                title=_("Duplicate Detection Warning"),
                indicator="orange",
                alert=True
            )
            
            # Also log to error log for reference
            frappe.log_error(
                title=f"Duplicate Detection - {doctype} Import",
                message=f"Found {warning_count} duplicates during import:\n" + 
                        "\n".join([f"- {val}" for val in duplicate_results.keys()])
            )
    
    except Exception as e:
        frappe.log_error(
            title="Duplicate Detection Error in Data Import",
            message=f"Error during duplicate detection: {str(e)}"
        )


def check_import_row_for_duplicate(doc, method=None):
    """
    Check individual import row for duplicates during processing.
    
    This is called for each row being imported to provide real-time
    duplicate detection feedback.
    
    Args:
        doc: The document being imported
        method: The method name
    """
    # Only run if this is from a data import
    if not frappe.flags.in_import:
        return
    
    doctype = doc.doctype
    
    if doctype not in ["Item Group", "Customer Group", "Brand", "Supplier Group"]:
        return
    
    # Check if duplicate detection is enabled
    if not is_duplicate_detection_enabled(doctype):
        return
    
    # Get the name field for this doctype
    name_field_map = {
        "Item Group": "item_group_name",
        "Customer Group": "customer_group_name",
        "Brand": "brand",
        "Supplier Group": "supplier_group_name"
    }
    
    name_field = name_field_map.get(doctype)
    if not name_field:
        return
    
    value = doc.get(name_field)
    if not value:
        return
    
    # Check for duplicates (this will show warning via msgprint)
    from kindlife_app.utils.duplicate_detector import check_duplicate
    
    check_duplicate(
        doctype=doctype,
        name_field=name_field,
        value=value,
        exclude_name=doc.name if not doc.is_new() else None
    )
