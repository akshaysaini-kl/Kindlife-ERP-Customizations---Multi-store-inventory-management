import frappe


@frappe.whitelist()
def get_current_user_type(user=None):
    """
    Returns the business channel type for the current user based on their roles.
    - Admin / Exempt roles  → 'Both'  (show B2B + B2C)
    - No channel role selected → 'Both'  (show B2B + B2C)
    - B2B role only → 'B2B'
    - B2C role only → 'B2C'
    - Both B2B & B2C roles → 'Both'
    """
    user = user or frappe.session.user
    roles = frappe.get_roles(user)

    # Admins / exempt roles see everything
    if any(r in roles for r in EXEMPT_ROLES):
        return "Both"

    allowed_types = {val for role, val in ROLE_TYPE_MAP.items() if role in roles}

    if not allowed_types:
        # No channel role assigned – treat as full access
        return "Both"

    if len(allowed_types) > 1:
        return "Both"

    return list(allowed_types)[0]

# ---------------- CONFIG ----------------
# "Role":"Type"
ROLE_TYPE_MAP = {
    "B2B": "B2B",
    "B2C": "B2C",

}


# Roles that can access all entries, role based filter dont apply to them
EXEMPT_ROLES = [
    "System Manager",
    "Administrator",
]

# These are the roles that block brand-fulfilled PO access
WAREHOUSE_ROLE = "Warehouse User"
# ----------------------------------------



# ----Generic Class
class BasePermissionHandler:
    """
    Logic in generic class
        - Check for user role and filter the fields based on B2B and B2C
        - If user has a admin role, give them all permissions and dont apply any filters
    """

    def is_user_exempt(self, user):
        """Checks for exempt roles."""
        user = user or frappe.session.user
        roles = frappe.get_roles(user)
        return any(r in roles for r in EXEMPT_ROLES)

    def get_allowed_types(self, user):
        user = user or frappe.session.user
        roles = frappe.get_roles(user)
        return {val for role, val in ROLE_TYPE_MAP.items() if role in roles}

    def get_filter_condition(self, user, doctype=None, conditions=None):
        """
        Finalizes the permission query conditions.
        """
        conditions = conditions or []

        if self.is_user_exempt(user):#This is most potent condition, if true, it will override all other logic
            return None

        allowed_types = self.get_allowed_types(user)
        prefix = f"`tab{doctype}`." if doctype else ""
        type_parts = [f"{prefix}custom_type = '{t}'" for t in allowed_types]  #makes conditions to check if custom type is in the list of allowed roles
        if type_parts:
            # Also allow access if custom_type is "Both"
            type_parts.append(f"{prefix}custom_type = 'Both'")
            type_condition = " OR ".join(type_parts)
            # Add parenthesis if there is more than one condition
            if len(type_parts) > 1:
                type_condition = f"({type_condition})"
            conditions.append(type_condition)

        if not conditions:
            return ""#If none of conditions are provided, return here
        print(" AND ".join(f"({c})" for c in conditions))
        return " AND ".join(f"({c})" for c in conditions)

    def has_permission(self, doc, user, child_permission=True):

        if self.is_user_exempt(user):
            return True
        if doc.is_new():
            return True


        if not child_permission:
            return False

        allowed_types = self.get_allowed_types(user)
        if not allowed_types:
            return True
        
        doc_val = doc.get("custom_type")
        if doc_val == "Both":
            return True
        return doc_val in allowed_types
