# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

"""
Duplicate Detection Utility for ERPNext Doctypes

This module provides fuzzy string matching functionality to detect potential
duplicate records based on name similarity. It uses the rapidfuzz library for
high-performance fuzzy matching.

Usage:
    from kindlife_app.utils.duplicate_detector import check_duplicate, get_similar_records
    
    # Check for duplicates and show warning
    check_duplicate("Item Group", "item_group_name", "Cashew & almonds", threshold=80)
    
    # Get list of similar records
    similar = get_similar_records("Customer", "customer_name", "ABC Corp", threshold=80)
"""

import frappe
from frappe import _
from rapidfuzz import fuzz
from typing import List, Dict, Optional, Tuple


@frappe.whitelist()
def check_duplicates_api(doctype: str, name_field: str, value: str, exclude_name: Optional[str] = None) -> Dict[str, any]:
    """
    API method to check for duplicates from Client Script.
    Returns details to show confirmation dialog.
    """
    if not value or not isinstance(value, str):
        return {}
        
    if not is_duplicate_detection_enabled(doctype):
        return {}

    threshold = get_configured_threshold() or 80
    similar_records = get_similar_records(doctype, name_field, value, exclude_name, threshold)
    
    if similar_records:
        return {
            "has_duplicates": True,
            "warning_message": format_duplicate_warning(doctype, similar_records, value),
            "records": similar_records
        }
    
    return {"has_duplicates": False}


def check_duplicate(
    doctype: str,
    name_field: str,
    value: str,
    exclude_name: Optional[str] = None,
    threshold: int = 80,
    from_import: bool = False
) -> bool:
    """
    Check for duplicate records.
    
    For Imports: Returns True (hooks validation handles the rest).
    For UI/API: Sends a standard warning message (alert) but DOES NOT BLOCK.
    Blocking verification is handled by Client Script via check_duplicates_api.
    """
    if not value or not isinstance(value, str):
        return False
    
    if not is_duplicate_detection_enabled(doctype):
        return False
    
    configured_threshold = get_configured_threshold()
    if configured_threshold:
        threshold = configured_threshold
    
    similar_records = get_similar_records(doctype, name_field, value, exclude_name, threshold)
    
    if similar_records:
        if from_import:
            return True
            
        # For UI/API, just show non-blocking alert
        warning_message = format_duplicate_warning(doctype, similar_records, value)
        frappe.msgprint(
            msg=warning_message,
            title=_("Potential Duplicate Detected"),
            indicator="orange",
            alert=True
        )
        return True
    
    return False


def get_similar_records(
    doctype: str,
    name_field: str,
    value: str,
    exclude_name: Optional[str] = None,
    threshold: int = 80
) -> List[Dict[str, any]]:
    """
    Get a list of similar records based on fuzzy string matching.
    
    This function retrieves all existing records and calculates similarity scores
    using the token_sort_ratio algorithm, which handles word order variations.
    
    Args:
        doctype: The DocType to search
        name_field: The field name to compare
        value: The value to compare against
        exclude_name: Optional name to exclude from results
        threshold: Minimum similarity percentage to include in results
    
    Returns:
        List of dictionaries containing similar records with their similarity scores.
        Each dict has keys: 'name', 'field_value', 'similarity'
    
    Example:
        >>> get_similar_records("Customer", "customer_name", "ABC Corp", threshold=80)
        [{'name': 'CUST-001', 'field_value': 'ABC Corporation', 'similarity': 85.5}]
    """
    # Use cache key for performance
    cache_key = f"duplicate_check_{doctype}_{name_field}"
    
    # Try to get from cache first
    cached_records = frappe.cache().get_value(cache_key)
    
    if cached_records is None:
        # Fetch all records from database
        filters = {}
        if exclude_name:
            filters["name"] = ["!=", exclude_name]
        
        try:
            existing_records = frappe.get_all(
                doctype,
                filters=filters,
                fields=["name", name_field],
                limit=0  # Get all records
            )
        except Exception as e:
            frappe.log_error(f"Error fetching records for duplicate detection: {str(e)}")
            return []
        
        # Cache for 5 minutes
        frappe.cache().set_value(cache_key, existing_records, expires_in_sec=300)
        cached_records = existing_records
    else:
        # If we have exclude_name, filter it out from cached results
        if exclude_name:
            cached_records = [r for r in cached_records if r.get("name") != exclude_name]
    
    similar_records = []
    value_lower = value.lower().strip()
    
    # Calculate similarity for each existing record
    for record in cached_records:
        existing_value = record.get(name_field)
        if not existing_value:
            continue
        
        existing_value_lower = existing_value.lower().strip()
        
        # Skip exact matches (case-insensitive)
        if value_lower == existing_value_lower:
            continue
        
        # Calculate similarity using token_sort_ratio (handles word order variations)
        similarity = fuzz.token_sort_ratio(value_lower, existing_value_lower)
        
        if similarity >= threshold:
            similar_records.append({
                "name": record.get("name"),
                "field_value": existing_value,
                "similarity": round(similarity, 1)
            })
    
    # Sort by similarity (highest first)
    similar_records.sort(key=lambda x: x["similarity"], reverse=True)
    
    return similar_records


def format_duplicate_warning(doctype: str, similar_records: List[Dict[str, any]], value: str) -> str:
    """
    Format a user-friendly warning message for duplicate records.
    
    Args:
        doctype: The DocType being checked
        similar_records: List of similar records with similarity scores
        value: The value entered by the user
    
    Returns:
        Formatted HTML message string
    """
    # Check for custom message template
    custom_template = get_custom_warning_template()
    if custom_template:
        return custom_template.format(doctype=doctype, records=similar_records, value=value)
    
    # Default message format
    message = _("You entered: <b>{0}</b>").format(value)
    message += "<br><br>"
    message += _("The following similar {0} records already exist:").format(_(doctype))
    message += "<br><br>"
    
    # Show top 5 matches
    for record in similar_records[:5]:
        # If field_value matches name (common for Item Group, Brand, etc), only show once
        if record['field_value'] == record['name']:
            record_info = f"<b>{record['field_value']}</b>"
        else:
            record_info = f"<b>{record['field_value']}</b> ({record['name']})"
            
        message += f"• {record_info} "
        message += f"({record['similarity']}% match)"
        message += f" - <a href='/app/{doctype.lower().replace(' ', '-')}/{record['name']}'>{_('View')}</a>"
        message += "<br>"
    
    if len(similar_records) > 5:
        message += f"<br><i>...and {len(similar_records) - 5} more similar record(s)</i><br>"
    
    return message


def is_duplicate_detection_enabled(doctype: str) -> bool:
    """
    Check if duplicate detection is enabled for a specific doctype.
    
    Args:
        doctype: The DocType to check
    
    Returns:
        True if enabled, False otherwise. Returns True by default if settings don't exist.
    """
    try:
        if not frappe.db.exists("DocType", "Kindlife Settings"):
            # Settings doctype doesn't exist yet, enable by default
            return True
        
        settings = frappe.get_cached_doc("Kindlife Settings")
        
        # Map doctype to settings field
        field_map = {
            "Item Group": "enabled_for_item_group",
            "Customer Group": "enabled_for_customer_group",
            "Brand": "enabled_for_brand",
            "Supplier Group": "enabled_for_supplier_group"
        }
        
        field_name = field_map.get(doctype)
        if field_name:
            return settings.get(field_name, 1)  # Default to enabled
        
        return True  # Enable for any doctype not in the map
    except Exception:
        # If settings don't exist or error occurs, enable by default
        return True


def get_configured_threshold() -> Optional[int]:
    """
    Get the configured similarity threshold from settings.
    
    Returns:
        Configured threshold value or None if not configured
    """
    try:
        if not frappe.db.exists("DocType", "Kindlife Settings"):
            return None
        
        settings = frappe.get_cached_doc("Kindlife Settings")
        threshold = settings.get("similarity_threshold")
        
        if threshold and 0 < threshold <= 100:
            return threshold
        
        return None
    except Exception:
        return None


def get_custom_warning_template() -> Optional[str]:
    """
    Get custom warning message template from settings.
    
    Returns:
        Custom template string or None if not configured
    """
    try:
        if not frappe.db.exists("DocType", "Kindlife Settings"):
            return None
        
        settings = frappe.get_cached_doc("Kindlife Settings")
        template = settings.get("warning_message_template")
        
        return template if template else None
    except Exception:
        return None


def clear_duplicate_detection_cache(doctype: str, name_field: str) -> None:
    """
    Clear the cache for duplicate detection for a specific doctype.
    
    This should be called after creating/updating/deleting records to ensure
    the cache stays fresh.
    
    Args:
        doctype: The DocType to clear cache for
        name_field: The field name used in caching
    """
    cache_key = f"duplicate_check_{doctype}_{name_field}"
    frappe.cache().delete_value(cache_key)


def batch_check_duplicates(
    doctype: str,
    name_field: str,
    values: List[str],
    threshold: int = 80
) -> Dict[str, List[Dict[str, any]]]:
    """
    Check multiple values for duplicates in a single operation.
    
    This is optimized for data imports where multiple records need to be checked.
    
    Args:
        doctype: The DocType to check
        name_field: The field name to compare
        values: List of values to check
        threshold: Similarity threshold percentage
    
    Returns:
        Dictionary mapping each value to its list of similar records
    
    Example:
        >>> batch_check_duplicates("Item Group", "item_group_name", 
        ...                        ["Mobile Phone", "Laptop"], threshold=80)
        {'Mobile Phone': [...], 'Laptop': [...]}
    """
    results = {}
    
    for value in values:
        similar = get_similar_records(doctype, name_field, value, threshold=threshold)
        if similar:
            results[value] = similar
    
    return results
