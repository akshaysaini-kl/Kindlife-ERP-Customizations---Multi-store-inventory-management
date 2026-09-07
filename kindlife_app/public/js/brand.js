frappe.ui.form.on('Brand', {
    refresh: function (frm) {
        // Set custom_disabled as read-only if it was disabled by rapid fuzz
        frm.set_df_property('custom_disabled', 'read_only', frm.doc.custom_disable_by_rapid_fuzz ? 1 : 0);
    },
    custom_disable_by_rapid_fuzz: function(frm) {
        frm.set_df_property('custom_disabled', 'read_only', frm.doc.custom_disable_by_rapid_fuzz ? 1 : 0);
    }
});
