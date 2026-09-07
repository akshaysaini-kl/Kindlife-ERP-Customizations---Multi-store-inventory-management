# Copyright (c) 2026, Auriga and contributors
# For license information, please see license.txt

"""
This fn is responsible for making the popup that shows list of similar Brands.
"""

import frappe
from frappe import _
import json


@frappe.whitelist()
def save_brand_with_bypass(**kwargs):
    """
    Save a Brand record with duplicate check bypassed.
    
    Args:
        brand_name: The brand name to save
        brand_doc: Optional JSON string of the full brand document
    
    Returns:
        JSON with success status and doc name
    """
    
    # Extract args from kwargs (Frappe passes server_action args in 'args' key)
    if 'args' in kwargs:
        args = kwargs.get('args')
        if isinstance(args, str):
            args = json.loads(args)
        brand_name = args.get('brand_name')
        brand_doc = args.get('brand_doc')
    else:
        brand_name = kwargs.get('brand_name')
        brand_doc = kwargs.get('brand_doc')
    
    if brand_doc:
        # Parse the document if provided
        doc_dict = brand_doc
        if isinstance(doc_dict, str):
            doc_dict = json.loads(doc_dict)
            
        # Get the document
        if doc_dict.get('name') and frappe.db.exists('Brand', doc_dict.get('name')):
            # Existing document - load and update
            doc = frappe.get_doc('Brand', doc_dict.get('name'))
            doc.update(doc_dict)
        else:
            # New document
            doc = frappe.get_doc(doc_dict)
    else:
        # Create new brand with just the name
        doc = frappe.get_doc({
            "doctype": "Brand",
            "brand": brand_name
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
        _("Brand '{0}' saved as 'Pending Approval' in disabled state.").format(doc.brand),
        indicator="orange",
        alert=True
    )
    # Originally these were needed as we were saving a document and it has not been saved in the database
    return {
        'success': True,
        'doc_name': doc.name
    }
