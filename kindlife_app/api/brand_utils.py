# File: your_app/your_app/api/brand_utils.py
# Create this file in your custom app

import frappe
from frappe.model.rename_doc import rename_doc
from frappe import _
import json

@frappe.whitelist()
def bulk_rename_brands(rename_data, merge_if_exists=False):
    """
    Bulk rename brands using Frappe's rename utility
    
    Args:
        rename_data (dict): Dictionary with old_name: new_name mapping
        merge_if_exists (bool): Whether to merge if target brand exists
    
    Returns:
        dict: Success/error status with details
    """
    if isinstance(rename_data, str):
        rename_data = json.loads(rename_data)
    if not isinstance(rename_data, dict):
        frappe.throw(_("Invalid rename data provided"))
    
    results = {
        'success': [],
        'errors': [],
        'total': len(rename_data)
    }
    
    for old_name, new_name in rename_data.items():
        try:
            # Validate that the old brand exists
            if not frappe.db.exists('Brand', old_name):
                results['errors'].append({
                    'old_name': old_name,
                    'new_name': new_name,
                    'error': f'Brand "{old_name}" does not exist'
                })
                continue
            
            # Check if new name already exists (when not merging)
            if not merge_if_exists and frappe.db.exists('Brand', new_name):
                results['errors'].append({
                    'old_name': old_name,
                    'new_name': new_name,
                    'error': f'Brand "{new_name}" already exists'
                })
                continue
            
            # Validate new name
            if not new_name or new_name.strip() == '':
                results['errors'].append({
                    'old_name': old_name,
                    'new_name': new_name,
                    'error': 'New name cannot be empty'
                })
                continue
            
            # Check permissions
            if not frappe.has_permission('Brand', 'write', old_name):
                results['errors'].append({
                    'old_name': old_name,
                    'new_name': new_name,
                    'error': f'No permission to rename "{old_name}"'
                })
                continue
            
            # Perform the rename
            rename_doc('Brand', old_name, new_name.strip(), merge=merge_if_exists)
            
            results['success'].append({
                'old_name': old_name,
                'new_name': new_name.strip()
            })
            
        except Exception as e:
            frappe.log_error(f"Error renaming brand {old_name} to {new_name}: {str(e)}")
            results['errors'].append({
                'old_name': old_name,
                'new_name': new_name,
                'error': str(e)
            })
    
    return results

@frappe.whitelist()
def validate_brand_names(names_to_check):
    """
    Validate if brand names exist and check permissions
    
    Args:
        names_to_check (list): List of brand names to validate
    
    Returns:
        dict: Validation results
    """
    if not isinstance(names_to_check, list):
        names_to_check = [names_to_check]
    
    results = {
        'valid': [],
        'invalid': [],
        'no_permission': []
    }
    
    for name in names_to_check:
        if frappe.db.exists('Brand', name):
            if frappe.has_permission('Brand', 'write', name):
                results['valid'].append(name)
            else:
                results['no_permission'].append(name)
        else:
            results['invalid'].append(name)
    
    return results