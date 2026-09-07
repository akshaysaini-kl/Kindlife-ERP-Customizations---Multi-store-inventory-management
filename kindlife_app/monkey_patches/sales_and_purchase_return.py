import erpnext.controllers.sales_and_purchase_return

original_validate_quantity = erpnext.controllers.sales_and_purchase_return.validate_quantity

def patched_validate_quantity(doc, key, args, ref, valid_items, already_returned_items):
    """
    Monkey patch to SKIP quantity validation specifically for Purchase Receipt Returns.
    """
    
    if doc.doctype == "Purchase Receipt" and doc.is_return:
        return

    return original_validate_quantity(doc, key, args, ref, valid_items, already_returned_items)
