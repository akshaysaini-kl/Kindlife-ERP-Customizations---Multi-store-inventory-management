from kindlife_app.services.permissions.base import BasePermissionHandler


class PurchaseInvoicePermissionHandler(BasePermissionHandler):
    pass


# Instantiate handler
handler = PurchaseInvoicePermissionHandler()


# Wrapper functions for hooks
def permission_query(user=None):
    doctype = "Purchase Invoice"
    return handler.get_filter_condition(user, doctype=doctype)

def has_permission(doc=None, ptype=None, user=None):
    if not doc: 
        return True
    return handler.has_permission(doc, user)
