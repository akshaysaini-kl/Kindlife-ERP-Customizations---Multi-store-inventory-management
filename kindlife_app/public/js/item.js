frappe.form.link_formatters['Item'] = function (value, doc) {
    if (doc.item_code && doc.item_name !== value) {
        return doc.item_code;
    } else {
        return value;
    }
};

frappe.ui.form.on('Item Price', {
    refresh: function (frm) {
        load_item_history(frm);
        
        // Allow emergency MRP edits on Item Price
        frappe.db.get_single_value('Kindlife Settings', 'allow_mrp_edit').then(val => {
            if (val) {
                frm.set_df_property('custom_buying_price', 'read_only', 0);
            }
        });
    },

    item_code: function (frm) {
        if (frm.doc.item_code) {
            load_item_history(frm);
        }
    },

    price_list: function (frm) {
        if (frm.doc.item_code && frm.doc.price_list) {
            load_item_history(frm);
        }
    },

    custom_buying_price: function (frm) {
        calculate_discount(frm);
    },

    custom_discount_percentage: function (frm) {
        calculate_discount(frm);
    },

    custom_discount_on: function (frm) {
        calculate_discount(frm);
    },

    price_list_rate: function (frm) {
        let custom_discount_on = frm.doc.custom_discount_on;
        if (custom_discount_on === 'Selling Price') {
            calculate_discount(frm);
        }
    }
});

function calculate_discount(frm) {
    let custom_discount_on = frm.doc.custom_discount_on;
    let discount_percentage = flt(frm.doc.custom_discount_percentage);

    if (!discount_percentage) return;

    if (custom_discount_on === 'MRP') {
        let custom_buying_price = flt(frm.doc.custom_buying_price);

        if (custom_buying_price > 0) {
            let discount_amount_precision = 2;

            // Try to get from field definition
            let df_amt = frappe.meta.get_docfield(frm.doc.doctype, 'custom_discount_amount');
            if (df_amt && df_amt.precision) discount_amount_precision = parseInt(df_amt.precision);

            let discount_amount = flt(custom_buying_price * (discount_percentage / 100.0), discount_amount_precision);
            frm.set_value('custom_discount_amount', discount_amount);
            // Do NOT update price_list_rate
        }
    } else if (custom_discount_on === 'Selling Price') {
        let price_list_rate = flt(frm.doc.price_list_rate);

        if (price_list_rate > 0) {
            let discount_amount_precision = 2;
            let df_amt = frappe.meta.get_docfield(frm.doc.doctype, 'custom_discount_amount');
            if (df_amt && df_amt.precision) discount_amount_precision = parseInt(df_amt.precision);

            let discount_amount = flt(price_list_rate * (discount_percentage / 100.0), discount_amount_precision);
            frm.set_value('custom_discount_amount', discount_amount);
            // price_list_rate is intentionally NOT updated
        }
    }
}

function load_item_history(frm) {
    if (!frm.doc.item_code) {
        frm.set_df_property('custom_history', 'options', '<p>Please select an item to view history</p>');
        return;
    }

    // Show loading message
    frm.set_df_property('custom_history', 'options', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Loading history...</div>');

    frappe.call({
        method: 'kindlife_app.api.item_price.get_item_price_history',
        args: {
            item_code: frm.doc.item_code,
            price_list: frm.doc.price_list || null
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                let html = generate_history_table(r.message);
                frm.set_df_property('custom_history', 'options', html);
            } else {
                frm.set_df_property('custom_history', 'options', '<p class="text-muted">No price history found for this item</p>');
            }
        },
        error: function () {
            frm.set_df_property('custom_history', 'options', '<p class="text-danger">Error loading price history</p>');
        }
    });
}

function generate_history_table(data) {
    let html = `
        <div class="item-price-history">
            <style>
                .item-price-history {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", sans-serif;
                }
                .history-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                    font-size: 12px;
                }
                .history-table th {
                    background-color: #f8f9fa;
                    color: #495057;
                    font-weight: 600;
                    padding: 12px 8px;
                    text-align: left;
                    border: 1px solid #dee2e6;
                    white-space: nowrap;
                }
                .history-table td {
                    padding: 10px 8px;
                    border: 1px solid #dee2e6;
                    vertical-align: middle;
                }
                .history-table tbody tr:nth-child(even) {
                    background-color: #f8f9fa;
                }
                .history-table tbody tr:hover {
                    background-color: #e9ecef;
                }
                .status-approved {
                    background-color: #d4edda;
                    color: #155724;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 500;
                }
                .status-rejected {
                    background-color: #f8d7da;
                    color: #721c24;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 500;
                }
                .status-pending {
                    background-color: #fff3cd;
                    color: #856404;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 500;
                }
                .currency {
                    text-align: left;
                    font-weight: 500;
                }
                .history-header {
                    margin-bottom: 15px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #007bff;
                }
                .history-title {
                    color: #007bff;
                    font-size: 16px;
                    font-weight: 600;
                    margin: 0;
                }
                .history-subtitle {
                    color: #6c757d;
                    font-size: 12px;
                    margin: 5px 0 0 0;
                }
            </style>
            
            <div class="history-header">
                <h4 class="history-title">Item Price History</h4>
                <p class="history-subtitle">Historical price changes and approvals</p>
            </div>
            
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Item Name</th>
                        <th>Price List</th>
                        <th>Buying Price</th>
                        <th>MRP</th>
                        <th>Requested By</th>
                        <th>Approved By</th>
                        <th>Valid From</th>
                        <th>Status</th>
                        <th>Modified</th>
                    </tr>
                </thead>
                <tbody>`;

    data.forEach(function (row) {
        let status_class = 'status-pending';
        let status_text = 'Pending';

        if (row.approval_status === 'Approved') {
            status_class = 'status-approved';
            status_text = 'Approved';
        } else if (row.approval_status === 'Rejected') {
            status_class = 'status-rejected';
            status_text = 'Rejected';
        }

        html += `
            <tr>
                <td><strong>${row.item_name || row.item_code}</strong></td>
                <td>${row.price_list || '-'}</td>
                <td class="currency">${get_currency_symbol(row.currency)} ${row.price_list_rate ? frappe.format(row.price_list_rate) : '-'}</td>
                <td class="currency">${get_currency_symbol(row.currency)} ${row.custom_buying_price ? frappe.format(row.custom_buying_price) : '-'}</td>
                <td>${row.requested_by || row.owner || '-'}</td>
                <td>${row.approved_by || '-'}</td>
                <td>${row.valid_from ? frappe.datetime.str_to_user(row.valid_from) : '-'}</td>
                <td><span class="${status_class}">${status_text}</span></td>
                <td>${row.modified ? frappe.datetime.str_to_user(row.modified) : '-'}</td>
            </tr>`;
    });

    html += `
                </tbody>
            </table>
        </div>`;

    return html;
}