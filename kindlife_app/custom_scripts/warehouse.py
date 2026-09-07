# my_custom_app/my_custom_app/overrides/warehouse_overrides.py
import frappe
from frappe.utils.nestedset import get_ancestors_of


def autoname_based_on_parent(doc, method):
    """
    Override the default autoname for Warehouse
    This function will traverse up the parent hierarchy 
    to find the first ancestor that has a "Warehouse Suffix".

    - If a suffix is found, the name is {warehouse_name} - {custom_warehouse_suffix}.
    - If no ancestor has a suffix, the name is just {warehouse_name}.
    - The group warehouse will also have suffixes

    The field "custom_warehouse_suffix" will only come if the warehouse is a main warehouse
    """

    if doc.parent_warehouse :
        suffix_to_use = None
        current_ancestor = doc.parent_warehouse 
        # This gives list of all parents in a list
        parent_list = get_ancestors_of("Warehouse", current_ancestor)
        parent_list = [current_ancestor] + parent_list


        parent_data = frappe.get_all(
            "Warehouse",
            filters={"name": ("in", parent_list)},
            fields=["name", "custom_warehouse_suffix"],
            order_by="lft desc"        # 'lft desc' ordering is to finding the CLOSEST parents first
        )

        # Iterate over all the data we got and stop when we get a suffix
        for parent in parent_data:
            if parent.custom_warehouse_suffix:
                suffix_to_use = parent.custom_warehouse_suffix
                # Found the closest one, so we can stop immediately.
                break

            

        # After the loop, format the name based on whether we found a suffix.
        if suffix_to_use:
            doc.name = f"{doc.warehouse_name} - {suffix_to_use}"
        else:
            # No suffix was found in the entire ancestry. Use the name as is.
            doc.name = doc.warehouse_name

    else:
        # For Group warehouses or root-level ledger warehouses, the name is just what was typed.
        doc.name = doc.warehouse_name
