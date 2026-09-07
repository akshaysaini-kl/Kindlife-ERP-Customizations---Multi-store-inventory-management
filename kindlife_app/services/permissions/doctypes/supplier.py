from kindlife_app.services.permissions.base import BasePermissionHandler


class SupplierPermissionHandler(BasePermissionHandler):
    pass


# Instantiate handler
handler = SupplierPermissionHandler()


# Wrapper functions for hooks
# Because of this, only suppliers matching the roles will be visible in the Purchase order supplier field
def permission_query(user=None):
    doctype = "Supplier"
    return handler.get_filter_condition(user, doctype=doctype)

def has_permission(doc=None, ptype=None, user=None):
    if not doc: 
        return True
    return handler.has_permission(doc, user)
