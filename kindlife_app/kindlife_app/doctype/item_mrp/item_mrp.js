// Copyright (c) 2026, Auriga IT and Contributors
// See license.txt

frappe.ui.form.on("Item MRP", {
    refresh(frm) {
        // Status badge colour
        if (frm.doc.status === "Applied") {
            frm.page.set_indicator(__("Applied"), "green");
        } else if (frm.doc.docstatus === 1) {
            frm.page.set_indicator(__("Pending"), "orange");
        }

        // Show a clear warning if effective_from is in the future
        if (frm.doc.docstatus === 1 && frm.doc.status === "Pending") {
            let msg = __(
                "This MRP change is scheduled to be applied on {0}.",
                [frappe.datetime.str_to_user(frm.doc.effective_from)]
            );
            frm.dashboard.add_comment(msg, "blue");
        }
    },
});
