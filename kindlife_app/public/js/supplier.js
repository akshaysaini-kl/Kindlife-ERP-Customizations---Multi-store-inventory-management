frappe.ui.form.on('Supplier', {
    refresh: function (frm) {
        set_custom_type_based_on_role(frm);
        // Filter Supplier Group to only show enabled records
        frm.set_query('supplier_group', () => {
            return {
                filters: {
                    custom_disabled: 0
                }
            };
        });
    },
    gst_transporter_id: function (frm) {
        set_pan_from_transporter_id(frm);
    },
    is_transporter: function (frm) {
        set_supplier_group(frm);
    }
});


function set_pan_from_transporter_id(frm) {
    let transporter_id = frm.doc.gst_transporter_id;
    if (transporter_id && transporter_id.length === 15) {
        let pan = transporter_id.slice(2, 12);
        try {
            // Reuse the validation logic from India Compliance to ensure PAN format is correct
            // This avoids hardcoding the PAN regex here
            let valid_pan = india_compliance.validate_pan(pan);
            if (valid_pan) {
                frm.set_value('pan', valid_pan);
            }
        } catch (e) {
            // If PAN is incorrect, it will automatically give error from built in code
        }
    }
}

function set_supplier_group(frm) {
    if (frm.doc.is_transporter) {
        frm.set_value('supplier_group', 'Transporter');
    } else {
        // Reset to empty if unchecked as requested
        frm.set_value('supplier_group', '');
    }
}
