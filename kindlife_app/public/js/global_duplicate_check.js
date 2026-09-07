/*
* Global Duplicate Check Handler
* 
* Checks for duplicates via API and shows a Yes/No confirmation dialog.
* If user clicks Yes, the record is saved.
* If user clicks No, the save is cancelled.
*/

const duplicate_check_handler = {
    validate: function (frm) {
        // If already confirmed or explicitly ignored, skip check
        if (frm.doc.__confirmed_duplicate || frm.doc.__ignore_duplicate_check) return;

        // Initialize fuzzy match flag
        frm.doc.__fuzzy_match_found = false;

        // Map doctypes to their name fields
        let name_field_map = {
            "Item Group": "item_group_name",
            "Customer Group": "customer_group_name",
            "Brand": "brand",
            "Supplier Group": "supplier_group_name"
        };

        let field = name_field_map[frm.doc.doctype];
        if (!field || !frm.doc[field]) return;

        // Only check if new record or if the name field has changed
        // For existing records, we check if the field value is different from what was loaded
        if (!frm.is_new() && !frm.is_dirty(field)) return;

        // Flag to indicate validation is in progress - strict blocking
        frappe.validated = false;

        frappe.call({
            method: "kindlife_app.utils.duplicate_detector.check_duplicates_api",
            args: {
                doctype: frm.doc.doctype,
                name_field: field,
                value: frm.doc[field],
                exclude_name: frm.is_new() ? "" : frm.doc.name
            },
            freeze: true,
            freeze_message: __("Checking for duplicates..."),
            callback: function (r) {
                if (r.message && r.message.has_duplicates) {
                    // Set flag for server-side use
                    frm.doc.__fuzzy_match_found = true;

                    // Show Confirmation Dialog (Yes/No)
                    frappe.confirm(
                        r.message.warning_message,
                        () => {
                            // YES: Proceed with save
                            frm.doc.__confirmed_duplicate = true;
                            frappe.validated = true;
                            // Use setTimeout to ensure the dialog closes before save
                            setTimeout(() => {
                                frm.save();
                            }, 100);
                        },
                        () => {
                            // NO: Cancel save
                            frappe.validated = false;
                            frappe.msgprint(__("Save cancelled by user."));
                        }
                    );
                } else {
                    // No duplicates, proceed with save
                    frm.doc.__confirmed_duplicate = true;
                    frappe.validated = true;
                    // Use setTimeout to ensure proper save re-triggering
                    setTimeout(() => {
                        frm.save();
                    }, 100);
                }
            }
        });
    }
};

// Register for target doctypes
frappe.ui.form.on("Item Group", duplicate_check_handler);
frappe.ui.form.on("Customer Group", duplicate_check_handler);
frappe.ui.form.on("Brand", duplicate_check_handler);
frappe.ui.form.on("Supplier Group", duplicate_check_handler);
