import frappe
from frappe import _

def before_save(doc, method):
    """
    Validation hook for Customer.
    """
    # 1. Derive PAN from GSTIN if not set
    if not doc.pan and doc.gstin:
        doc.pan = doc.gstin[2:12]

    # Force PAN to uppercase if set
    if doc.pan:
        doc.pan = doc.pan.upper()

    # 2. Validate Mandatory Fields
    validate_mandatory_fields(doc)

    # 3. Validate PAN consistency with GSTIN
    validate_pan_consistency(doc)

    # 4. Check for Duplicate Customers based on PAN
    validate_customer_uniqueness(doc)

def validate_pan_consistency(doc):
    if doc.gstin and doc.pan and len(doc.gstin) >= 15:
        # Check if PAN matches the one in GSTIN
        derived_pan = doc.gstin[2:12].upper()
        if derived_pan != doc.pan:
            frappe.throw(
                _("PAN '{0}' does not match the PAN extracted from GSTIN '{1}'.").format(
                    doc.pan, derived_pan
                ),
                frappe.ValidationError
            )

def validate_mandatory_fields(doc):
    if doc.territory == "India":
        if doc.custom_type != "B2C" and not doc.pan:
            frappe.throw(_("PAN is mandatory for non-B2C customers in India"))

def validate_customer_uniqueness(doc):
    if not doc.pan:
        return

    # Check if a customer with the same PAN already exists
    duplicates = frappe.db.sql("""
        SELECT name, customer_name
        FROM `tabCustomer`
        WHERE pan = %(pan)s
        AND name != %(name)s
    """, {
        'pan': doc.pan,
        'name': doc.name
    }, as_dict=True)

    if duplicates:
        links = []
        for d in duplicates:
            customer_name = d.customer_name or d.name
            links.append(f"<a href='/app/customer/{d.name}' target='_blank'>{customer_name}</a>")
        
        customer_list = ", ".join(links)
        
        msg = _("The following customers already use the PAN {0}: {1}").format(
            frappe.bold(doc.pan), customer_list
        )
        
        frappe.throw(msg, title=_("Duplicate Customer Error"))
