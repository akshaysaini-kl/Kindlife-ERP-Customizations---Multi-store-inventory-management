frappe.query_reports["Current Item Price"] = {
    "filters": [
        {
            "fieldname": "price_list",
            "label": __("Price List"),
            "fieldtype": "Link",
            "options": "Price List",
            "reqd": 1
        }
    ],

    "onload": function (report) {
        // Add button for pending approval report
        report.page.add_inner_button(__('Pending Approval Prices'), function () {
            frappe.set_route('query-report', 'Pending Item Price Approval', {
                'price_list': frappe.query_report.get_filter_value('price_list')
            });
        });
    },



    //    "formatter": function(value, row, column, data, default_formatter) {
    //         if (column.fieldname == "pending_count") {
    //             if (value > 0) {
    //                 return `<div style="text-align: center;">
    //                             <span class="badge badge-warning" 
    //                                  style="cursor: pointer; font-size: 10px; padding: 3px 6px; border-radius: 10px;"
    //                                  onclick="viewPendingPrices('${data.item_code}', '${frappe.query_report.get_filter_value('price_list')}')"
    //                                  title="Click to view ${value} pending approval(s)">
    //                                 <i class="fa fa-clock-o" style="font-size: 9px;"></i> ${value}
    //                             </span>
    //                         </div>`;
    //             } else {
    //                 return `<div style="text-align: center;">
    //                             <span class="badge badge-success" 
    //                                   style="font-size: 10px; padding: 3px 6px; border-radius: 10px;">
    //                                 <i class="fa fa-check" style="font-size: 9px;"></i> 0
    //                             </span>
    //                         </div>`;
    //             }
    //         }
    //         return default_formatter(value, row, column, data);
    //     }
};

// Global functions for actions
window.changePrice = function (item_code, price_list) {
    let dialog = new frappe.ui.Dialog({
        title: __('Change Item Price'),
        fields: [
            {
                fieldname: 'item_code',
                label: __('Item Code'),
                fieldtype: 'Link',
                options: 'Item',
                default: item_code,
                read_only: 1
            },
            {
                fieldname: 'price_list',
                label: __('Price List'),
                fieldtype: 'Link',
                options: 'Price List',
                default: price_list,
                read_only: 1
            },
            {
                fieldname: 'new_buying_price',
                label: __('New Buying Price'),
                fieldtype: 'Currency',
                reqd: 1,
                onchange: function () {
                    calculate_discount_dialog(this.dialog);
                }
            },
            {
                fieldname: 'new_mrp',
                label: __('New MRP'),
                fieldtype: 'Currency',
                reqd: 1,
                onchange: function () {
                    calculate_discount_dialog(this.dialog);
                }
            },
            {
                fieldname: 'custom_discount_on',
                label: __('Discount On'),
                fieldtype: 'Select',
                options: 'Selling Price\nMRP',
                default: 'Selling Price',
                onchange: function () {
                    calculate_discount_dialog(this.dialog);
                }
            },
            {
                fieldname: 'custom_discount_percentage',
                label: __('Discount Percentage'),
                fieldtype: 'Float',
                onchange: function () {
                    calculate_discount_dialog(this.dialog);
                }
            },
            {
                fieldname: 'custom_discount_amount',
                label: __('Discount Amount'),
                fieldtype: 'Float',
                onchange: function () {
                    // reverse_calculate_discount_dialog(this.dialog); // Optional: Implement if needed
                }
            },
            {
                fieldname: 'valid_from',
                label: __('Valid From'),
                fieldtype: 'Date',
                default: frappe.datetime.get_today(),
                reqd: 1
            }
        ],
        primary_action_label: __('Save and Submit'),
        primary_action: function (values) {
            frappe.call({
                method: 'kindlife_app.api.item_price.create_item_price_for_approval',
                args: values,
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint(__('Price changes submitted'));
                        dialog.hide();
                        frappe.query_report.refresh();
                    }
                }
            });
        }
    });

    dialog.show();
};

function calculate_discount_dialog(dialog) {
    let values = dialog.get_values();
    let custom_discount_on = values.custom_discount_on;
    let discount_percentage = flt(values.custom_discount_percentage);

    if (!discount_percentage) return;

    if (custom_discount_on === 'MRP') {
        let custom_buying_price = flt(values.new_mrp);

        if (custom_buying_price > 0) {
            let discount_amount = flt(custom_buying_price * (discount_percentage / 100.0), 2);
            dialog.set_value('custom_discount_amount', discount_amount);

            // Update buying price (price_list_rate)
            let new_rate = flt(custom_buying_price - discount_amount, 2);
            dialog.set_value('new_buying_price', new_rate);
        }
    } else if (custom_discount_on === 'Selling Price') {
        let price_list_rate = flt(values.new_buying_price);

        if (price_list_rate > 0) {
            let discount_amount = flt(price_list_rate * (discount_percentage / 100.0), 2);
            dialog.set_value('custom_discount_amount', discount_amount);
            // Do NOT update price_list_rate recursively
        }
    }
}

window.viewPendingPrices = function (item_code, price_list) {
    frappe.set_route('query-report', 'Pending Item Price Approval', {
        'price_list': price_list,
        'item_code': item_code,
    });
};