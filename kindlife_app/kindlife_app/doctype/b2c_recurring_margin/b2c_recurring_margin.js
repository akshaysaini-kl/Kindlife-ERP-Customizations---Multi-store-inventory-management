// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.ui.form.on("B2C Recurring Margin", {
    item_code(frm) {
        if (!frm.doc.item_code) {
            frm.set_value("supplier", "");
            return;
        }

        frappe.call({
            method: "kindlife_app.kindlife_app.doctype.b2c_recurring_margin.b2c_recurring_margin.get_default_supplier_for_item",
            args: { item_code: frm.doc.item_code },
            callback(r) {
                if (r.message) {
                    frm.set_value("supplier", r.message);
                } else {
                    frm.set_value("supplier", "");
                    frappe.msgprint(__("No default supplier found for item {0}", [frm.doc.item_code]));
                }
            },
        });
    },
});
