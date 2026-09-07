# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

"""
Validation hooks for duplicate detection across ERPNext doctypes.

This module provides validation functions that are called via Frappe's
doc_events hooks system to check for duplicate records during creation
and updates.
"""

import frappe
from frappe import _
import json
from kindlife_app.utils.duplicate_detector import (
    check_duplicate, 
    clear_duplicate_detection_cache,
    get_similar_records,
    get_configured_threshold,
    is_duplicate_detection_enabled
)
from frappe import local


# Generic Workflow Functions (shared by all doctypes)

def handle_workflow_transition(doc):
    """
    Handle field updates when the workflow state changes.
    Only acts on Approved transition. Cancelled leaves all fields untouched.
    Works for any doctype with custom_disabled and custom_disable_by_rapid_fuzz fields.
    """
    if doc.is_new():
        return

    previous_state = None
    if doc._doc_before_save:
        previous_state = doc._doc_before_save.workflow_state

    if not doc.workflow_state or not previous_state:
        return

    if doc.workflow_state != previous_state:
        new_state = doc.workflow_state

        if new_state == "Approved":
            doc.custom_disabled = 0
            doc.custom_disable_by_rapid_fuzz = 0

        # Cancelled: Do nothing — fields stay as-is


def set_workflow_state_after_insert(doc, method=None):
    """
    After insert: Frappe's workflow engine forces 'Pending Approval' during insert.
    This corrects the state:
    - No fuzzy match: skip straight to 'Approved' via direct DB update
    - Fuzzy match found: keep 'Pending Approval' (already set by workflow engine)
    """
    if not doc.custom_disable_by_rapid_fuzz:
        # Update both DB and in-memory object to ensure consistency in UI response
        doc.workflow_state = "Approved"
        doc.custom_disabled = 0
        doc.custom_disable_by_rapid_fuzz = 0
        
        frappe.db.set_value(doc.doctype, doc.name, {
            "workflow_state": "Approved",
            "custom_disabled": 0,
            "custom_disable_by_rapid_fuzz": 0
        }, update_modified=False)


def process_fuzzy_check(doc, field_name, value, exclude_name=None):
    """
    Shared logic for running fuzzy duplicate detection and setting penalty flags.
    Returns similar_records list if any found.
    """
    if not is_duplicate_detection_enabled(doc.doctype):
        return []

    threshold = get_configured_threshold() or 80
    similar_records = get_similar_records(
        doctype=doc.doctype,
        name_field=field_name,
        value=value,
        exclude_name=exclude_name,
        threshold=threshold
    )

    if similar_records:
        # Apply Mandatory Penalty: Disabled + Pending Approval
        doc.custom_disabled = 1
        doc.custom_disable_by_rapid_fuzz = 1
        doc.workflow_state = "Pending Approval"
        
        if exclude_name: # Signal that it's a rename operation
            frappe.db.set_value(doc.doctype, exclude_name, {
                "custom_disabled": 1,
                "custom_disable_by_rapid_fuzz": 1,
                "workflow_state": "Pending Approval"
            })
            
    return similar_records



def validate_item_group_duplicate(doc, method=None):
    """
    Validate Item Group for potential duplicates.
    
    Logic:
    1. Handle workflow state transitions (Approved/Cancelled).
    2. Default to 'Approved' and 'Enabled' for new records or name changes.
    3. Run duplicate check.
    4. If duplicates found and not confirmed, show warning and block save.
    5. If duplicates found and confirmed (__confirmed_duplicate), silently set flags.
    """
    # Handle workflow transitions first (cleans fields if Approved)
    handle_workflow_transition(doc)

    # Track if user has confirmed to proceed despite duplicates
    confirmed_duplicate = doc.get("__confirmed_duplicate")
    
    if doc.item_group_name:
        # Step 1: For new records or name changes, reset flags
        # Always assume the entry is valid, unless proven otherwise
        is_val_changed = doc.has_value_changed("item_group_name")
        if doc.is_new() or is_val_changed:
            doc.custom_disabled = 0
            doc.custom_disable_by_rapid_fuzz = 0
        else:
            # Existing record with no name change, don't re-validate
            return

        # Step 3: Run the check on the server
        similar_records = process_fuzzy_check(
            doc=doc,
            field_name="item_group_name",
            value=doc.item_group_name,
            exclude_name=doc.name if not doc.is_new() else None
        )
        fuzzy_match_found = True if similar_records else False
        
        if fuzzy_match_found:
            # --- OVERRIDE: DUPLICATE DETECTED ---
            doc.custom_disabled = 1
            doc.custom_disable_by_rapid_fuzz = 1
            doc.workflow_state = "Pending Approval"

            # If user already confirmed via the JS duplicate check dialog,
            # just set the flags silently and allow the save to proceed
            if confirmed_duplicate:
                return

            from_import = frappe.flags.in_import or frappe.flags.in_data_import or False
            if not from_import:
                # For UI, show msgprint with server action for bypass
                message = f"<b>You are trying to create: '{doc.item_group_name}'</b><br><br>"
                message += "<b>Similar Item Group records already exist:</b><br><br>"
                
                for record in similar_records[:5]:
                    message += f"• <b>{record['field_value']}</b> ({record['similarity']}% match) - <a href='/app/item-group/{record['name']}'>{record['name']}</a><br>"
                
                if len(similar_records) > 5:
                    message += f"<br><i>...and {len(similar_records) - 5} more similar record(s)</i><br>"
                
                message += "<br>" + _("This record will be saved in a <b>disabled state</b> as <b>Pending Approval</b>.")
                message += "<br><br>" + _("Do you want to save anyway?")
                
                frappe.msgprint(
                    msg=message,
                    title=_("Potential Duplicate Item Group Detected"),
                    indicator="orange",
                    primary_action={
                        'label': _('Save Anyway'),
                        'server_action': 'kindlife_app.api.item_group_api.save_item_group_with_bypass',
                        'args': {
                            'item_group_name': doc.item_group_name,
                            'item_group_doc': json.loads(frappe.as_json(doc))
                        }
                    }
                )
                # Block current save
                raise frappe.ValidationError(_("Similar record detected. Please review the duplicate warning."))


def validate_customer_group_duplicate(doc, method=None):
    """
    Validate Customer Group for potential duplicates.
    
    Logic:
    1. Handle workflow state transitions (Approved/Cancelled).
    2. Default to 'Approved' and 'Enabled' for new records or name changes.
    3. Run duplicate check.
    4. If duplicates found and not confirmed, show warning and block save.
    5. If duplicates found and confirmed (__confirmed_duplicate), silently set flags.
    """
    # Handle workflow transitions first (cleans fields if Approved)
    handle_workflow_transition(doc)

    # Track if user has confirmed to proceed despite duplicates
    confirmed_duplicate = doc.get("__confirmed_duplicate")
    
    if doc.customer_group_name:
        # Step 1: For new records or name changes, reset flags
        is_val_changed = doc.has_value_changed("customer_group_name")
        if doc.is_new() or is_val_changed:
            doc.custom_disabled = 0
            doc.custom_disable_by_rapid_fuzz = 0
        else:
            # Existing record with no name change, don't re-validate
            return

        # Step 3: Run the check on the server
        similar_records = process_fuzzy_check(
            doc=doc,
            field_name="customer_group_name",
            value=doc.customer_group_name,
            exclude_name=doc.name if not doc.is_new() else None
        )
        fuzzy_match_found = True if similar_records else False
        
        if fuzzy_match_found:
            # --- OVERRIDE: DUPLICATE DETECTED ---
            doc.custom_disabled = 1
            doc.custom_disable_by_rapid_fuzz = 1
            doc.workflow_state = "Pending Approval"

            # If user already confirmed via the JS duplicate check dialog,
            # just set the flags silently and allow the save to proceed
            if confirmed_duplicate:
                return

            from_import = frappe.flags.in_import or frappe.flags.in_data_import or False
            if not from_import:
                # For UI, show msgprint with server action for bypass
                message = f"<b>You are trying to create: '{doc.customer_group_name}'</b><br><br>"
                message += "<b>Similar Customer Group records already exist:</b><br><br>"
                
                for record in similar_records[:5]:
                    message += f"• <b>{record['field_value']}</b> ({record['similarity']}% match) - <a href='/app/customer-group/{record['name']}'>{record['name']}</a><br>"
                
                if len(similar_records) > 5:
                    message += f"<br><i>...and {len(similar_records) - 5} more similar record(s)</i><br>"
                
                message += "<br>" + _("This record will be saved in a <b>disabled state</b> as <b>Pending Approval</b>.")
                message += "<br><br>" + _("Do you want to save anyway?")
                
                frappe.msgprint(
                    msg=message,
                    title=_("Potential Duplicate Customer Group Detected"),
                    indicator="orange",
                    primary_action={
                        'label': _('Save Anyway'),
                        'server_action': 'kindlife_app.api.customer_group_api.save_customer_group_with_bypass',
                        'args': {
                            'customer_group_name': doc.customer_group_name,
                            'customer_group_doc': json.loads(frappe.as_json(doc))
                        }
                    }
                )
                # Block current save
                raise frappe.ValidationError(_("Similar record detected. Please review the duplicate warning."))








def validate_brand_duplicate(doc, method=None):
    """
    Validate Brand for potential duplicates.
    
    Logic:
    1. Handle workflow state transitions (Approved/Cancelled).
    2. Default to 'Approved' and 'Enabled' for new records or name changes.
    3. Run duplicate check.
    4. If duplicates found and not confirmed, show warning and block save.
    5. If duplicates found and confirmed (__confirmed_duplicate), silently set flags.
    """
    # Handle workflow transitions first (cleans fields if Approved)
    handle_workflow_transition(doc)

    # Track if user has confirmed to proceed despite duplicates
    confirmed_duplicate = doc.get("__confirmed_duplicate")
    
    if doc.brand:
        # Step 1: For new records or name changes, reset flags
        is_val_changed = doc.has_value_changed("brand")
        if doc.is_new() or is_val_changed:
            doc.custom_disabled = 0
            doc.custom_disable_by_rapid_fuzz = 0
        else:
            # Existing record with no name change, don't re-validate
            return

        # Step 3: Run the check on the server
        similar_records = process_fuzzy_check(
            doc=doc,
            field_name="brand",
            value=doc.brand,
            exclude_name=doc.name if not doc.is_new() else None
        )
        fuzzy_match_found = True if similar_records else False
        
        if fuzzy_match_found:
            # --- OVERRIDE: DUPLICATE DETECTED ---
            doc.custom_disabled = 1
            doc.custom_disable_by_rapid_fuzz = 1
            doc.workflow_state = "Pending Approval"

            # If user already confirmed via the JS duplicate check dialog,
            # just set the flags silently and allow the save to proceed
            if confirmed_duplicate:
                return

            from_import = frappe.flags.in_import or frappe.flags.in_data_import or False
            if not from_import:
                # For UI, show msgprint with server action for bypass
                message = f"<b>You are trying to create: '{doc.brand}'</b><br><br>"
                message += "<b>Similar Brand records already exist:</b><br><br>"
                
                for record in similar_records[:5]:
                    message += f"• <b>{record['field_value']}</b> ({record['similarity']}% match) - <a href='/app/brand/{record['name']}'>{record['name']}</a><br>"
                
                if len(similar_records) > 5:
                    message += f"<br><i>...and {len(similar_records) - 5} more similar record(s)</i><br>"
                
                message += "<br>" + _("This record will be saved in a <b>disabled state</b> as <b>Pending Approval</b>.")
                message += "<br><br>" + _("Do you want to save anyway?")
                
                frappe.msgprint(
                    msg=message,
                    title=_("Potential Duplicate Brand Detected"),
                    indicator="orange",
                    primary_action={
                        'label': _('Save Anyway'),
                        'server_action': 'kindlife_app.api.brand_api.save_brand_with_bypass',
                        'args': {
                            'brand_name': doc.brand,
                            'brand_doc': json.loads(frappe.as_json(doc))
                        }
                    }
                )
                raise frappe.ValidationError(_("Please review the duplicate warning."))




def validate_supplier_group_duplicate(doc, method=None):
    """
    Validate Supplier Group for potential duplicates.
    
    Logic:
    1. Handle workflow state transitions (Approved/Cancelled).
    2. Default to 'Approved' and 'Enabled' for new records or name changes.
    3. Run duplicate check.
    4. If duplicates found and not confirmed, show warning and block save.
    5. If duplicates found and confirmed (__confirmed_duplicate), silently set flags.
    """
    # Handle workflow transitions first (cleans fields if Approved)
    handle_workflow_transition(doc)

    # Track if user has confirmed to proceed despite duplicates
    confirmed_duplicate = doc.get("__confirmed_duplicate")
    
    if doc.supplier_group_name:
        # Step 1: For new records or name changes, reset flags
        is_val_changed = doc.has_value_changed("supplier_group_name")
        if doc.is_new() or is_val_changed:
            doc.custom_disabled = 0
            doc.custom_disable_by_rapid_fuzz = 0
        else:
            # Existing record with no name change, don't re-validate
            return

        # Step 3: Run the check on the server
        similar_records = process_fuzzy_check(
            doc=doc,
            field_name="supplier_group_name",
            value=doc.supplier_group_name,
            exclude_name=doc.name if not doc.is_new() else None
        )
        fuzzy_match_found = True if similar_records else False
        
        if fuzzy_match_found:
            # --- OVERRIDE: DUPLICATE DETECTED ---
            doc.custom_disabled = 1
            doc.custom_disable_by_rapid_fuzz = 1
            doc.workflow_state = "Pending Approval"

            # If user already confirmed via the JS duplicate check dialog,
            # just set the flags silently and allow the save to proceed
            if confirmed_duplicate:
                return

            from_import = frappe.flags.in_import or frappe.flags.in_data_import or False
            if not from_import:
                # For UI, show msgprint with server action for bypass
                message = f"<b>You are trying to create: '{doc.supplier_group_name}'</b><br><br>"
                message += "<b>Similar Supplier Group records already exist:</b><br><br>"
                
                for record in similar_records[:5]:
                    message += f"• <b>{record['field_value']}</b> ({record['similarity']}% match) - <a href='/app/supplier-group/{record['name']}'>{record['name']}</a><br>"
                
                if len(similar_records) > 5:
                    message += f"<br><i>...and {len(similar_records) - 5} more similar record(s)</i><br>"
                
                message += "<br>" + _("This record will be saved in a <b>disabled state</b> as <b>Pending Approval</b>.")
                message += "<br><br>" + _("Do you want to save anyway?")
                
                frappe.msgprint(
                    msg=message,
                    title=_("Potential Duplicate Supplier Group Detected"),
                    indicator="orange",
                    primary_action={
                        'label': _('Save Anyway'),
                        'server_action': 'kindlife_app.api.supplier_group_api.save_supplier_group_with_bypass',
                        'args': {
                            'supplier_group_name': doc.supplier_group_name,
                            'supplier_group_doc': json.loads(frappe.as_json(doc))
                        }
                    }
                )
                # Block current save
                raise frappe.ValidationError(_("Similar record detected. Please review the duplicate warning."))


def clear_cache_on_update(doc, method=None):
    """
    Clear duplicate detection cache when a record is created/updated/deleted.
    
    This ensures the cache stays fresh and new duplicates are detected.
    
    Args:
        doc: The document being updated
        method: The method name (on_update, on_trash, etc.)
    """
    doctype_field_map = {
        "Item Group": "item_group_name",
        "Customer Group": "customer_group_name",
        "Brand": "brand",
        "Supplier Group": "supplier_group_name"
    }
    
    if doc.doctype in doctype_field_map:
        field_name = doctype_field_map[doc.doctype]
        clear_duplicate_detection_cache(doc.doctype, field_name)

def validate_before_rename(doc, method, old, new, merge=False):
    """
    Validate rename operation for potential duplicates.
    Called via the before_rename hook for supported doctypes.
    """
    if merge:
        #not part of the flow
        return

    # 1. Identify name field for the doctype
    doctype_field_map = {
        "Item Group": "item_group_name",
        "Customer Group": "customer_group_name",
        "Brand": "brand",
        "Supplier Group": "supplier_group_name"
    }

    if doc.doctype not in doctype_field_map:
        return

    name_field = doctype_field_map[doc.doctype]
    
    # 2. Run fuzzy match check on the NEW name
    similar_records = process_fuzzy_check(
        doc=doc,
        field_name=name_field,
        value=new,
        exclude_name=old
    )

    if similar_records:
        # Build warning message
        message = f"<b>You are renaming '{old}' to: '{new}'</b><br><br>"
        message += f"<b>Similar {doc.doctype} records already exist:</b><br><br>"
        
        route_name = doc.doctype.lower().replace(" ", "-")
        for record in similar_records[:5]:
            message += f"• <a href='/app/{route_name}/{record['name']}'><b>{record['field_value']}</b></a> ({record['similarity']}% match)<br>"
        
        if len(similar_records) > 5:
            message += f"<br><i>...and {len(similar_records) - 5} more similar record(s)</i><br>"
        
        message += "<br>" + _("This record has been automatically <b>Disabled</b> and set to <b>Pending Approval</b> because of the similarity.")
        
        frappe.msgprint(
            msg=message,
            title=_("Potential Duplicate Detected during Rename"),
            indicator="orange"
        )
