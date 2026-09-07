import frappe
from kindlife_app.services.permissions.base import BasePermissionHandler, WAREHOUSE_ROLE


class PurchaseOrderPermissionHandler(BasePermissionHandler):
    """
    Logic in PO specific class
        - If user is a warehouse user, then they should not see POs that are brand fullfilled
    """
    def get_filter_condition(self, user, doctype=None, conditions=None):
        conditions = conditions or []

        prefix = f"`tab{doctype}`." if doctype else ""
        roles = frappe.get_roles(user or frappe.session.user)
        if WAREHOUSE_ROLE in roles:
            conditions.append(f"{prefix}custom_is_brand_fulfilled = 0")
        print("Conditions", conditions)
        return super().get_filter_condition(user, doctype=doctype, conditions=conditions)

    def has_permission(self, doc, user):
        roles = frappe.get_roles(user or frappe.session.user)
        brand_val = doc.get("custom_is_brand_fulfilled")
        if WAREHOUSE_ROLE in roles and brand_val:
            child_decision = False
        else:
            child_decision = True

        return super().has_permission(doc, user, child_permission=child_decision)


# Instantiate handler
handler = PurchaseOrderPermissionHandler()


# Wrapper functions for hooks
def permission_query(user=None):
    doctype = "Purchase Order"
    return handler.get_filter_condition(user, doctype=doctype)

def has_permission(doc=None, ptype=None, user=None):
    if not doc: 
        return True
    return handler.has_permission(doc, user)
