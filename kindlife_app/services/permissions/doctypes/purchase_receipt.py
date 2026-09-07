from kindlife_app.services.permissions.base import BasePermissionHandler


class PurchaseReceiptPermissionHandler(BasePermissionHandler):
    pass


# Instantiate handler
handler = PurchaseReceiptPermissionHandler()


# Wrapper functions for hooks
def permission_query(user=None):
    doctype = "Purchase Receipt"
    return handler.get_filter_condition(user, doctype=doctype)

def has_permission(doc=None, ptype=None, user=None):
    if not doc: 
        return True
    return handler.has_permission(doc, user)
