frappe.ui.form.on('Customer', {
    refresh: function (frm) {
        // Filter Customer Group to only show enabled records
        frm.set_query('customer_group', () => {
            return {
                filters: {
                    custom_disabled: 0
                }
            };
        });
    }
});
