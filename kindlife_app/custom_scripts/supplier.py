import frappe
from frappe import _

@frappe.whitelist()
def check_supplier_uniqueness(name, pan):
    """
    Check if a supplier with the same PAN already exists.
    Returns a list of matching suppliers.
    """
    matches = []
    
    if not pan:
        return matches

    # Query for suppliers with the same PAN
    pan_matches = frappe.db.sql("""
        SELECT name, supplier_name, gstin, pan, gst_transporter_id
        FROM `tabSupplier`
        WHERE name != %(name)s
        AND pan = %(pan)s
    """, {
        'name': name if name else 'New Supplier',
        'pan': pan
    }, as_dict=True)

    for m in pan_matches:
        m['match_reason'] = 'Matching PAN'
        matches.append(m)

    return matches

def before_save(doc, method):
    """
    before_save event hook for Supplier. Checks for uniqueness and sets group.
    """
    # Enforce Supplier Group based on is_transporter
    set_supplier_group(doc, method)

    # Step 1: Validate Mandatory Fields
    validate_mandatory_fields(doc)

    # Step 2: Derive PAN if not set
    if not doc.pan:
        if doc.gstin and len(doc.gstin) >= 12:
            doc.pan = doc.gstin[2:12]
        elif doc.gst_transporter_id and len(doc.gst_transporter_id) == 15:
            doc.pan = doc.gst_transporter_id[2:12]

    # Force PAN to uppercase if set
    if doc.pan:
        doc.pan = doc.pan.upper()

    # Step 3: Validate PAN consistency with GSTIN
    validate_pan_consistency(doc)

    # Step 4: Validate Supplier Uniqueness
    validate_supplier_uniqueness(doc)

def validate_mandatory_fields(doc):
    if doc.country == "India" and not doc.pan:
        frappe.throw(_("PAN is mandatory for suppliers from India"))

    if doc.is_transporter and not doc.gst_transporter_id:
        frappe.throw(_("GST Transporter ID is mandatory for Transporters"))

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
            
    if doc.gst_transporter_id and doc.pan and len(doc.gst_transporter_id) >= 15:
        # Check if PAN matches the one in GST Transporter ID
        derived_pan = doc.gst_transporter_id[2:12].upper()
        if derived_pan != doc.pan:
            frappe.throw(
               _("PAN '{0}' does not match the PAN extracted from GST Transporter ID '{1}'.").format(
                    doc.pan, derived_pan
                ),
                frappe.ValidationError 
            )

def validate_supplier_uniqueness(doc):
    if doc.pan:
        matches = check_supplier_uniqueness(doc.name, doc.pan)
        
        if matches:
            # Build Simple List for the error message
            links = []
            for m in matches:
                supplier_name = m['supplier_name'] or m['name']
                links.append(f"<a href='/app/supplier/{m['name']}' target='_blank'>{supplier_name}</a>")
            
            supplier_list = ", ".join(links)
            
            msg = _("The following suppliers already use the PAN {0}: {1}").format(
                frappe.bold(doc.pan), supplier_list
            )
            
            frappe.throw(msg, title=_("Duplicate Supplier Error"))


def set_supplier_group(doc, method):
    """
    Set supplier group based on is_transporter
    """
    if doc.is_transporter:
        doc.supplier_group = "Transporter"
    elif not doc.supplier_group: 
         pass