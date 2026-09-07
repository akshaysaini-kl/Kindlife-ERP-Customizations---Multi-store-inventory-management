frappe.ui.form.on('Supplier Group', {
    refresh: function (frm) {
        // Filter Parent Supplier Group to only show enabled records
        frm.set_query('parent_supplier_group', () => {
            return {
                filters: {
                    custom_disabled: 0
                }
            };
        });
        // Set custom_disabled as read-only if it was disabled by rapid fuzz
        frm.set_df_property('custom_disabled', 'read_only', frm.doc.custom_disable_by_rapid_fuzz ? 1 : 0);
    },
    custom_disable_by_rapid_fuzz: function(frm) {
        frm.set_df_property('custom_disabled', 'read_only', frm.doc.custom_disable_by_rapid_fuzz ? 1 : 0);
    }
});
