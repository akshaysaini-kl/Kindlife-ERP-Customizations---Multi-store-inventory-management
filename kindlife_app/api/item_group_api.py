# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

"""
This fn is responcible for making the popup that shows list of similar Item groups.
"""

import frappe
from frappe import _
import json


@frappe.whitelist()
def save_item_group_with_bypass(**kwargs):
    """
    Save an Item Group record with duplicate check bypassed.
    
    Args:
        item_group_name: The item group name to save
        item_group_doc: Optional JSON string of the full item group document
    
    Returns:
        JSON with success status and doc name
    """
    import json
    
    # Extract args from kwargs (Frappe passes server_action args in 'args' key)
    if 'args' in kwargs:
        args = kwargs.get('args')
        if isinstance(args, str):
            args = json.loads(args)
        item_group_name = args.get('item_group_name')
        item_group_doc = args.get('item_group_doc')
    else:
        item_group_name = kwargs.get('item_group_name')
        item_group_doc = kwargs.get('item_group_doc')
    
    if item_group_doc:
        # Parse the document if provided
        doc_dict = item_group_doc
        if isinstance(doc_dict, str):
            doc_dict = json.loads(doc_dict)
            
        # Get the document
        if doc_dict.get('name') and frappe.db.exists('Item Group', doc_dict.get('name')):
            # Existing document - load and update
            doc = frappe.get_doc('Item Group', doc_dict.get('name'))
            

            doc.update(doc_dict)
        else:
            # New document
            doc = frappe.get_doc(doc_dict)
    else:
        # Create new item group with just the name
        doc = frappe.get_doc({
            "doctype": "Item Group",
            "item_group_name": item_group_name
        })
    
    # Set indicators for bypass and workflow
    doc.custom_disabled = 1
    doc.custom_disable_by_rapid_fuzz = 1
    doc.workflow_state = "Pending Approval"
    doc.__confirmed_duplicate = 1
    
    # Save the document, ignoring permissions to avoid workflow permission errors
    doc.save(ignore_permissions=True)
    
    # Show success message
    frappe.msgprint(
        _("Item Group '{0}' saved as 'Pending Approval' in disabled state.").format(doc.item_group_name),
        indicator="orange",
        alert=True
    )

    return {
        'success': True,
        'doc_name': doc.name
    }