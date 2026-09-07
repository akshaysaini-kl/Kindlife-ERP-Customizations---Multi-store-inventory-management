# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

"""
Server-side API methods for Customer Group duplicate detection and bypass.
"""

import frappe
from frappe import _
import json


@frappe.whitelist()
def save_customer_group_with_bypass(**kwargs):
    """
    Save a Customer Group record with duplicate check bypassed.
    
    Args:
        customer_group_name: The customer group name to save
        customer_group_doc: Optional JSON string of the full customer group document
    
    Returns:
        JSON with success status and doc name
    """
    
    # Extract args from kwargs
    if 'args' in kwargs:
        args = kwargs.get('args')
        if isinstance(args, str):
            args = json.loads(args)
        customer_group_name = args.get('customer_group_name')
        customer_group_doc = args.get('customer_group_doc')
    else:
        customer_group_name = kwargs.get('customer_group_name')
        customer_group_doc = kwargs.get('customer_group_doc')
    
    if customer_group_doc:
        # Parse the document if provided
        doc_dict = customer_group_doc
        if isinstance(doc_dict, str):
            doc_dict = json.loads(doc_dict)
            
        # Get the document
        if doc_dict.get('name') and frappe.db.exists('Customer Group', doc_dict.get('name')):
            # Existing document - load and update
            doc = frappe.get_doc('Customer Group', doc_dict.get('name'))
            doc.update(doc_dict)
        else:
            # New document
            doc = frappe.get_doc(doc_dict)
    else:
        # Create new customer group with just the name
        doc = frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": customer_group_name
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
        _("Customer Group '{0}' saved as 'Pending Approval' in disabled state.").format(doc.customer_group_name),
        indicator="orange",
        alert=True
    )

    return {
        'success': True,
        'doc_name': doc.name
    }
