from kindlife_app.services.permissions.base import BasePermissionHandler


class DeliveryNotePermissionHandler(BasePermissionHandler):
    pass


# Instantiate handler
handler = DeliveryNotePermissionHandler()


# Wrapper functions for hooks
def permission_query(user=None):
    doctype = "Delivery Note"
    return handler.get_filter_condition(user, doctype=doctype)

def has_permission(doc=None, ptype=None, user=None):
    if not doc: 
        return True
    return handler.has_permission(doc, user)
