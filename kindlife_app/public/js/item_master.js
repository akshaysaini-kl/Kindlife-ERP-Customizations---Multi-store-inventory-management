frappe.ui.form.on('Item', {
    refresh: function (frm) {
        // Filter Item Group to only show enabled records
        frm.set_query('item_group', () => {
            return {
                filters: {
                    custom_disabled: 0
                }
            };
        });

        // Filter Brand to only show enabled records
        frm.set_query('brand', () => {
            return {
                filters: {
                    custom_disabled: 0
                }
            };
        });
        // Set Item Name as read-only for existing items
        frm.set_df_property('item_name', 'read_only', frm.doc.__islocal ? 0 : 1);
        
        // Make MRP read-only for existing items (unless override is enabled)
        frappe.db.get_single_value('Kindlife Settings', 'allow_mrp_edit').then(val => {
            frm.set_df_property('custom_mrp', 'read_only', val ? 0 : (frm.doc.__islocal ? 0 : 1));
        });

        // Add "Edit MRP" button
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__('Edit MRP'), function() {
                let d = new frappe.ui.Dialog({
                    title: 'Edit MRP',
                    fields: [
                        {
                            label: 'New MRP',
                            fieldname: 'new_mrp',
                            fieldtype: 'Currency',
                            reqd: 1
                        },
                        {
                            label: 'Effective From',
                            fieldname: 'effective_from',
                            fieldtype: 'Date',
                            default: frappe.datetime.get_today(),
                            reqd: 1
                        }
                    ],
                    size: 'small',
                    primary_action_label: 'Submit',
                    primary_action(values) {
                        frappe.call({
                            method: 'kindlife_app.api.item_mrp.create_item_mrp',
                            args: {
                                item_code: frm.doc.name,
                                new_mrp: values.new_mrp,
                                effective_from: values.effective_from
                            },
                            freeze: true,
                            callback: function(r) {
                                if (!r.exc) {
                                    frappe.show_alert({message: __('MRP Edit request submitted.'), indicator: 'green'});
                                    frm.reload_doc();
                                    d.hide();
                                }
                            }
                        });
                    }
                });
                d.show();
            }, __('Actions'));
        }

        render_mrp_history(frm);
    },

    is_stock_item: function (frm) {
        if (frm.doc.is_stock_item) {
            frm.set_value('has_serial_no', 1);
            frm.set_value('has_batch_no', 1);
            frm.set_value('serial_no_series', 'KB.####');
        } else {
            frm.set_value('has_serial_no', 0);
            frm.set_value('has_batch_no', 0);
            frm.set_value('serial_no_series', '');
        }
    }
});

function render_mrp_history(frm) {
    if (frm.doc.__islocal || !frm.fields_dict.custom_mrp_history_html) return;
    
    frappe.call({
        method: 'kindlife_app.api.item_mrp.get_mrp_history',
        args: { item_code: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                let html = `<table class="table table-bordered">
                    <thead><tr>
                        <th>ID</th><th>Old MRP</th><th>New MRP</th><th>Effective From</th><th>Status</th><th>Submitted By</th><th>Date</th>
                    </tr></thead><tbody>`;
                
                if (r.message.length === 0) {
                    html += `<tr><td colspan="7" class="text-muted text-center">No MRP history found.</td></tr>`;
                } else {
                    r.message.forEach(row => {
                        let status_color = row.status === 'Applied' ? 'green' : 'orange';
                        let display_status = row.status;
                        
                        if (row.docstatus === 0) {
                            display_status = 'Draft';
                            status_color = 'red';
                        } else if (row.docstatus === 2) {
                            display_status = 'Cancelled';
                            status_color = 'grey';
                        }
                        
                        html += `<tr>
                            <td><a href="/app/item-mrp/${row.name}">${row.name}</a></td>
                            <td>${format_currency(row.old_mrp || 0, 'INR')}</td>
                            <td>${format_currency(row.new_mrp, 'INR')}</td>
                            <td>${frappe.datetime.str_to_user(row.effective_from)}</td>
                            <td><span class="indicator ${status_color}">${display_status}</span></td>
                            <td>${row.owner}</td>
                            <td>${frappe.datetime.str_to_user(row.creation)}</td>
                        </tr>`;
                    });
                }
                html += `</tbody></table>`;
                
                $(frm.fields_dict.custom_mrp_history_html.wrapper).html(html);
            }
        }
    });
}
