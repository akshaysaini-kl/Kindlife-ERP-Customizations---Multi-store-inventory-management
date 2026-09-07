// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.ui.form.on('CS Cart Sync Log', {
    refresh: function (frm) {
        if (frm.doc.status === 'Failed' || frm.doc.status === 'Success') {
            frm.add_custom_button(__('Retry Sync'), function () {
                frm.call({
                    method: 'retry_sync',
                    doc: frm.doc,
                    callback: function (r) {
                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass('btn-primary');
        }

        // Add indicator color
        if (frm.doc.status === 'Success') {
            frm.set_intro(__('Sync Successful'), 'green');
        } else if (frm.doc.status === 'Failed') {
            frm.set_intro(__('Sync Failed: ' + (frm.doc.message || '')), 'red');
        } else if (frm.doc.status === 'Queued' || frm.doc.status === 'Processing') {
            frm.set_intro(__('Sync in progress...'), 'orange');
        }
    }
});
