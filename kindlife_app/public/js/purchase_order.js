frappe.ui.form.on('Purchase Order Item', {
    item_code: function (frm, cdt, cdn) {
        // Hide edit icons for warehouse-only users when items are added/modified
        setTimeout(() => {
            if (is_warehouse_only_user()) {
                hide_item_row_edit_icons(frm);
            }
        }, 100);
    },
    price_list_rate: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
        setTimeout(() => {
            check_and_show_price_change_button(frm);
        }, 500);
    },
    custom_list_price: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
    },
    custom_free_item: function (frm, cdt, cdn) {
        set_free_item(frm, cdt, cdn);
    }
});

frappe.ui.form.on('Purchase Order', {
    onload: function (frm) {
        set_custom_type_based_on_role(frm);

        set_item_filter(frm);
        frm.set_query('custom_signature', () => {
            return { filters: { 'user': frappe.session.user, 'docstatus': 1 } };
        });
        frm.set_query('custom_stamp', () => {
            return { filters: { 'docstatus': 1 } };
        });


    },
    setup: function (frm) {

        let df = frappe.meta.docfield_map['Purchase Order Item']['custom_list_price'];
        df.formatter = function (value, df, options, doc) {
            // value--> data that will be in the field
            // df --> col details
            // options --> details
            // doc --> row data
            // While no data is added, place 0.00 as data
            if (!doc || !doc.custom_ip_name) {
                return `${get_currency_symbol(frm.doc.currency)}${value}`;
            }
            const ip_name = doc.custom_ip_name;
            const url = `/app/item-price/${ip_name}`;
            return `<a href="${url}" target="_blank" data-doctype="Item Price" data-name="${ip_name}" onclick="event.stopPropagation()">${get_currency_symbol(frm.doc.currency)} ${value}</a>`;

        }
    },

    buying_price_list: function (frm) {
        frm.events.update_mrp_based_on_currency(frm);
        frm.doc.items.forEach(item => {
            // Trigger item refresh to fetch new MRP from updated price list
        });
    },
    refresh: function (frm) {

        frm.set_df_property('custom_signature', 'only_select', true)
        frm.set_df_property('custom_stamp', 'only_select', true)

        // Display linked documents at the top of the form
        if (frm.doc.docstatus === 1) {
            display_linked_documents(frm);
        }

        // Add standalone buttons FIRST (before ERPNext adds its buttons)
        if (frm.doc.docstatus === 1) {
            // Add standalone Purchase Receipt button
            add_purchase_receipt_button(frm);

            // Add standalone Purchase Invoice button (only if user is not warehouse-only user)
            // if (!is_warehouse_only_user()) {
            //     add_purchase_invoice_button(frm);
            // }
        }

        setTimeout(() => {
            // Try hiding by label
            frm.page.clear_primary_action(); // Optional: if it's a primary action
            frm.page.clear_secondary_action(); // Optional: clears the secondary action

            // Try hiding by jQuery selector (if button still appears)
            // $(".btn:contains('Update Items')").hide();

            // Hide row edit icons for warehouse-only users
            if (is_warehouse_only_user()) {
                hide_item_row_edit_icons(frm);
            }
            frm.remove_custom_button('Product Bundle', 'Get Items From');
            frm.remove_custom_button('Material Request', 'Get Items From');
            frm.remove_custom_button('Supplier Quotation', 'Get Items From');
            frm.remove_custom_button('Update Rate as per Last Purchase', 'Tools');
            frm.remove_custom_button('Link to Material Request', 'Tools');
            // Remove Purchase Receipt and Purchase Invoice buttons from Create dropdown
            if (frm.doc.docstatus === 1) {
                frm.remove_custom_button('Purchase Receipt', 'Create');
                // frm.remove_custom_button('Purchase Invoice', 'Create');

                // Hide buttons for warehouse-only users (users with only Warehouse User role)
                if (is_warehouse_only_user()) {
                    // Remove Purchase Invoice button if it was added by ERPNext
                    frm.remove_custom_button('Purchase Invoice', 'Create');

                    // Remove Payment and Payment Request buttons
                    frm.remove_custom_button('Payment');
                    frm.remove_custom_button('Payment Request');
                    frm.remove_custom_button('Payment', 'Create');
                    frm.remove_custom_button('Payment Request', 'Create');
                    frm.remove_custom_button('Hold', 'Status');
                    frm.remove_custom_button('Close', 'Status');
                }
            }

            if (frm.doc.docstatus === 0 && !frm.is_new()) {
                add_price_review_button(frm);
            }
        }, 500);
        update_mrp_label(frm);
        inject_custom_css();
    },

    before_workflow_action: function (frm) {
        // Intercept workflow actions to show price comparison for Purchase Manager
        if (frm.selected_workflow_action && frm.selected_workflow_action.includes('Approve')) {
            return new Promise((resolve, reject) => {
                check_price_changes_before_approval(frm, resolve, reject);
            });
        }
    },

    currency: function (frm) {
        update_mrp_label(frm);
        frm.events.update_mrp_based_on_currency(frm);
        frm.fields_dict.items.grid.refresh();
    },
    conversion_rate: function (frm) {
        frm.events.update_mrp_based_on_currency(frm);
        frm.fields_dict.items.grid.refresh();
    },
    update_mrp_based_on_currency: function (frm) {
        const rate = frm.doc.conversion_rate || 1;

        frm.doc.items.forEach((item, idx) => {
            if (item.custom_mrpcompany_currency && rate > 0) {
                // Convert MRP from company currency (INR) to transaction currency
                // custom_mrpcompany_currency is in INR
                // conversion_rate is from transaction currency to company currency
                // So divide by conversion_rate to get transaction currency value
                let new_mrp = flt(item.custom_mrpcompany_currency / rate, 2);
                
                // Use frappe.model.set_value to trigger the custom_list_price event
                // which will automatically recalculate the margin
                frappe.model.set_value(item.doctype, item.name, 'custom_list_price', new_mrp);
            }
        });

        frm.refresh_field('items');
    },
    supplier: function (frm) {
        set_item_filter(frm);
        if (!frm.doc.supplier) return;

        // Call server-side method to fetch price lists from Item Price for this supplier
        frappe.call({
            method: 'kindlife_app.api.item.get_price_lists_for_supplier',
            args: {
                supplier: frm.doc.supplier
            },
            callback: function (r) {
                if (r.message) {
                    frm.set_query('buying_price_list', () => {
                        return {
                            filters: [
                                ['Price List', 'name', 'in', r.message],
                                ['Price List', 'buying', '=', 1]
                            ]
                        };
                    });
                }
            }
        });
    },
    buying_price_list: function (frm) {
        if (!frm.doc.supplier) return;

        // Call server-side method to fetch price lists from Item Price for this supplier
        frappe.call({
            method: 'kindlife_app.api.item.get_price_lists_for_supplier',
            args: {
                supplier: frm.doc.supplier
            },
            callback: function (r) {
                if (r.message) {
                    frm.set_query('buying_price_list', () => {
                        return {
                            filters: [
                                ['Price List', 'name', 'in', r.message],
                                ['Price List', 'buying', '=', 1]
                            ]
                        };
                    });
                }
            }
        });
    },
});


function inject_custom_css() {
    // Check if style already exists to prevent duplicate insertion on refresh
    if ($('#custom-po-css').length > 0) return;

    const css = `
            /* Sets constant size for preview images of signature and stamp */
            .frappe-control[data-fieldname="custom_signature_preview"] img,
            .frappe-control[data-fieldname="custom_stamp_preview"] img
            {
            max-width: 180px !important;
            max-height: 80px !important;
            }
    `;

    $('<style id="custom-po-css">')
        .prop('type', 'text/css')
        .html(css)
        .appendTo('head');
}





function set_free_item(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (row.custom_free_item) {
        frappe.model.set_value(cdt, cdn, 'price_list_rate', null);
    }

}

function set_item_filter(frm) {
    if (frm.doc.supplier) {
        // Set query filter for item selection
        frm.set_query("item_code", "items", function () {
            return {
                query: "kindlife_app.api.purchase_order.get_items_by_supplier",
                filters: {
                    supplier: frm.doc.supplier
                }
            };
        });
    } else {
        // Remove filter if no supplier selected
        frm.set_query("item_code", "items", function () {
            return {};
        });
    }
}

function calculate_custom_margin(cdt, cdn) {
    let row = locals[cdt][cdn];
    let custom_list_price = flt(row.custom_list_price);
    let buyer_price = flt(row.price_list_rate);

    if (custom_list_price > 0) {
        let margin = ((custom_list_price - buyer_price) / custom_list_price) * 100;
        console.log("margin", margin);
        frappe.model.set_value(cdt, cdn, 'custom_margin', flt(margin, 2));
    }
}

function update_mrp_label(frm) {
    let currency = frm.doc.currency || "Currency";
    frm.fields_dict["items"].grid.update_docfield_property(
        "custom_list_price", "label", `MRP (${currency})`
    );
}



function check_and_show_price_change_button(frm) {
    if (frm.doc.docstatus !== 0) return;
    if (frm.is_new()) return;

    frappe.call({
        method: "kindlife_app.api.po_price_change.check_price_changes_exist",
        args: {
            purchase_order_name: frm.doc.name
        },
        callback: function (r) {
            if (r.message) {
                // Price changes exist, show the button
                show_price_review_button(frm, true);
            } else {
                // No price changes, hide the button
                show_price_review_button(frm, false);
            }
        }
    });
}

function add_price_review_button(frm) {
    frappe.call({
        method: "kindlife_app.api.po_price_change.check_price_changes_exist",
        args: {
            purchase_order_name: frm.doc.name
        },
        callback: function (r) {
            if (r.message) {
                // Price changes exist, show approval dialog
                frm.add_custom_button(__('Review Price Changes'), function () {
                    show_price_comparison_dialog(frm, false);
                }).addClass('btn-primary');

                // Store reference to the button
                frm.price_review_button = frm.page.btn_secondary.find('[data-label="Review%20Price%20Changes"]').parent();
            } else {
                // No price changes, proceed with normal approval
                resolve();
            }
        },
        error: function () {
            reject();
        }
    });

}

function show_price_review_button(frm, show) {
    if (frm.price_review_button) {
        if (show) {
            frm.price_review_button.show();
        } else {
            frm.price_review_button.hide();
        }
    }
}

function check_price_changes_before_approval(frm, resolve, reject) {
    frappe.call({
        method: "kindlife_app.api.po_price_change.check_price_changes_exist",
        args: {
            purchase_order_name: frm.doc.name
        },
        callback: function (r) {
            if (r.message) {
                // Price changes exist, show approval dialog
                show_price_comparison_dialog(frm, true, resolve, reject);
            } else {
                // No price changes, proceed with normal approval
                resolve();
            }
        },
        error: function () {
            reject();
        }
    });
}

function show_price_comparison_dialog(frm, is_approval_flow = false, resolve = null, reject = null) {
    frappe.call({
        method: "kindlife_app.api.po_price_change.get_price_changes",
        args: {
            purchase_order_name: frm.doc.name
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                create_price_comparison_dialog(frm, r.message, is_approval_flow, resolve, reject);
            }
        },
        // error: function() {
        //     if (is_approval_flow && reject) reject();
        // }
    });
}

function create_price_comparison_dialog(frm, price_changes, is_approval_flow, resolve, reject) {
    let dialog_title = is_approval_flow ? __('Approve Purchase Order - Price Changes Review') : __('Price Changes Review');

    let dialog = new frappe.ui.Dialog({
        title: dialog_title,
        fields: [
            {
                fieldname: 'price_changes_html',
                fieldtype: 'HTML'
            }
        ],
        size: 'large',
        primary_action_label: is_approval_flow ? __('Approve Purchase Order') : __('Close'),
        primary_action: function (values) {
            if (is_approval_flow) {
                let create_prices = dialog.get_value('create_new_prices') || false;
                handle_approval_with_price_changes(frm, price_changes, create_prices, dialog, resolve, reject);
            } else {
                dialog.hide();
            }
        }
    });

    // Generate HTML for price comparison table
    let html = generate_price_comparison_html(price_changes, is_approval_flow, frm);
    dialog.fields_dict.price_changes_html.$wrapper.html(html);

    // Add checkbox for approval flow
    if (is_approval_flow) {
        dialog.fields_dict.price_changes_html.$wrapper.append(`
            <div class="form-group" style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #d1d8dd;">
                <div class="checkbox">
                    <label>
                        <input type="checkbox" id="create_new_prices"> 
                        <strong>${__('Create new Item Prices with updated rates')}</strong>
                    </label>
                </div>
                <small class="text-muted">${__('If checked, new Item Price records will be created in approved state with the updated rates.')}</small>
            </div>
        `);

        // Store checkbox value in dialog
        dialog.fields_dict.price_changes_html.$wrapper.find('#create_new_prices').on('change', function () {
            dialog.create_new_prices = $(this).is(':checked');
        });

        dialog.get_value = function (fieldname) {
            if (fieldname === 'create_new_prices') {
                return this.create_new_prices || false;
            }
            return frappe.ui.Dialog.prototype.get_value.call(this, fieldname);
        };
    }

    dialog.show();
    frappe.dom.unfreeze();
}



function generate_price_comparison_html(price_changes, is_approval_flow, frm) {
    let total_items = price_changes.length;
    let increase_count = price_changes.filter(item => item.percentage_change > 0).length;
    let decrease_count = price_changes.filter(item => item.percentage_change < 0).length;

    let html = `
        <div class="price-comparison-container">
            <div class="row" style="margin-bottom: 15px;">
                <div class="col-md-12">
                    <div class="alert alert-info">
                        <strong>${__('Price Changes Summary:')}</strong> 
                        ${total_items} ${__('items with price changes')} 
                        (${increase_count} ${__('increases')}, ${decrease_count} ${__('decreases')})
                    </div>
                </div>
            </div>
            
            <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                <table class="table table-bordered">
                    <thead style="position: sticky; top: 0; background: white; z-index: 10;">
                        <tr>
                            <th>${__('Item Code')}</th>
                            <th>${__('Item Name')}</th>
                            <th>${__('UOM')}</th>
                            <th>${__('Price List Rate')}</th>
                            <th>${__('New Price')}</th>
                            <th>${__('Change %')}</th>
                            <th>${__('Impact')}</th>
                        </tr>
                    </thead>
                    <tbody>
    `;

    price_changes.forEach(item => {
        let change_class = item.percentage_change > 0 ? 'text-danger' : 'text-success';
        let change_icon = item.percentage_change > 0 ? '↑' : '↓';
        let impact = (item.new_price - item.current_price) * item.qty;
        let impact_class = impact > 0 ? 'text-danger' : 'text-success';

        html += `
            <tr>
                <td><strong>${item.item_code}</strong></td>
                <td>${item.item_name || ''}</td>
                <td>${item.uom}</td>
                <td>${get_currency_symbol(frm.doc.currency)} ${frappe.format(item.current_price).toFixed(2)}</td>
                <td>${get_currency_symbol(frm.doc.currency)} ${frappe.format(item.new_price).toFixed(2)}</td>
                <td class="${change_class}">
                    <strong>${change_icon} ${Math.abs(item.percentage_change).toFixed(2)}%</strong>
                </td>
                <td class="${impact_class}">
                    <strong>${get_currency_symbol(frm.doc.currency)} ${frappe.format(impact).toFixed(2)}</strong>
                </td>
            </tr>
        `;
    });

    html += `
                    </tbody>
                </table>
            </div>
        </div>
    `;

    return html;
}

function handle_approval_with_price_changes(frm, price_changes, create_prices, dialog, resolve, reject) {
    if (create_prices) {
        // Create new item prices first
        frappe.call({
            method: "kindlife_app.api.po_price_change.create_new_item_prices",
            args: {
                purchase_order_name: frm.doc.name,
                price_changes_json: JSON.stringify(price_changes)
            },
            callback: function (r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Item Prices Created'),
                        message: __('Successfully created {0} new Item Price records.', [r.message.created_count]),
                        indicator: 'green'
                    });
                    dialog.hide();
                    if (resolve) resolve();
                } else {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('Failed to create Item Prices: {0}', [r.message.error || 'Unknown error']),
                        indicator: 'red'
                    });
                    if (reject) reject();
                }
            },
            error: function () {
                frappe.msgprint(__('Error creating Item Prices'));
                if (reject) reject();
            }
        });
    } else {
        // Proceed with approval without creating prices
        dialog.hide();
        if (resolve) resolve();
    }
}

// Add standalone Purchase Receipt button
function add_purchase_receipt_button(frm) {
    // Check if items allow receipt (not drop-shipped)
    let allow_receipt = false;
    for (let item of frm.doc.items || []) {
        if (item.delivered_by_supplier !== 1) {
            allow_receipt = true;
            break;
        }
    }

    if (!allow_receipt) return;

    // Check if PO is closed or on hold
    if (frm.doc.status === 'Closed' || frm.doc.status === 'On Hold') return;

    // Check if not fully received
    if (flt(frm.doc.per_received) < 100) {
        // Show "Create Purchase Receipt" button
        frm.add_custom_button(__('Create Purchase Receipt'), function () {
            frappe.model.open_mapped_doc({
                method: "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
                frm: frm
            });
        }).addClass('btn-primary');
    }
}

// Add standalone Purchase Invoice button
function add_purchase_invoice_button(frm) {
    // Check if PO is closed or on hold
    if (frm.doc.status === 'Closed' || frm.doc.status === 'On Hold') return;

    // Check if not fully billed
    if (flt(frm.doc.per_billed) < 100) {
        // Show "Create Purchase Invoice" button
        frm.add_custom_button(__('Create Purchase Invoice'), function () {
            frappe.model.open_mapped_doc({
                method: "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
                frm: frm
            });
        }).addClass('btn-primary');
    }
}

// Display linked Purchase Receipts, Purchase Invoices, and Stock Entries in tabular format
function display_linked_documents(frm) {
    // Use existing API to fetch linked documents (avoids permission errors)
    frappe.call({
        method: 'kindlife_app.api.purchase_order.get_draft_documents_count',
        args: {
            purchase_order: frm.doc.name
        },
        callback: function (r) {
            if (r.message) {
                let pr_data = r.message.all_pr_data || [];
                let pi_data = r.message.all_pi_data || [];
                let se_data = r.message.all_se_data || [];

                // Build tabular HTML for linked documents
                let html = build_linked_documents_table(pr_data, pi_data, se_data);

                // Set HTML in custom_related_links field
                frm.set_df_property('custom_related_links', 'options', html);
                frm.refresh_field('custom_related_links');

                // Add click handlers for collapsible rows
                setTimeout(() => {
                    setup_collapsible_handlers();
                }, 100);
            }
        }
    });
}

// Build the tabular HTML structure with collapsible rows
function build_linked_documents_table(pr_data, pi_data, se_data) {
    let html = `
        <div style="margin-bottom: 10px; padding: 12px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #2490ef;">
            <h5 style="margin-bottom: 15px; color: #2490ef; font-weight: 600;">📋 Related Documents</h5>
    `;

    // Check if any documents exist
    if (pr_data.length === 0 && pi_data.length === 0 && se_data.length === 0) {
        html += '<span style="color: #888; font-style: italic;">No related documents created yet.</span>';
    } else {
        html += `
            <table class="table table-bordered" style="margin-bottom: 0; background: white;">
                <thead style="background: #f1f3f4;">
                    <tr>
                        <th style="width: 50px; text-align: center;"></th>
                        <th style="width: 60px;">Type</th>
                        <th>Document</th>
                        <th style="width: 180px;">Status</th>
                    </tr>
                </thead>
                <tbody>
        `;

        // Add Purchase Receipts
        pr_data.forEach((pr, idx) => {
            // Use workflow_state if available, otherwise fall back to status
            let display_status = pr.workflow_state || pr.status;

            // Color coding based on workflow states
            let status_color;
            switch (display_status) {
                case 'Draft':
                    status_color = '#6c757d'; // Gray
                    break;
                case 'Pending QC':
                    status_color = '#ff9800'; // Orange
                    break;
                case 'Pending Putaway':
                    status_color = '#007bff'; // Blue
                    break;
                case 'Completed':
                    status_color = '#28a745'; // Green
                    break;
                default:
                    // Fallback to docstatus-based coloring for non-workflow states
                    status_color = pr.docstatus === 0 ? '#ff9800' : '#28a745';
            }

            let row_id = `pr-${idx}`;

            html += `
                <tr class="collapsible-row" data-target="${row_id}" style="cursor: pointer;">
                    <td style="text-align: center;">
                        <i class="fa fa-chevron-right expand-icon" style="color: #666;"></i>
                    </td>
                    <td><span style="color: #2490ef; font-weight: 500;">📦 PR</span></td>
                    <td>
                        <a href="/app/purchase-receipt/${pr.name}" target="_blank" 
                           style="color: #2490ef; text-decoration: none; font-weight: 500;">${pr.name}</a>
                    </td>
                    <td>
                        <span style="color: ${status_color}; font-weight: 500;">${display_status}</span>
                    </td>
                </tr>
                <tr id="${row_id}" class="collapsible-content" style="display: none;">
                    <td colspan="4" style="padding: 15px; background: #f9f9f9;">
                        ${build_pr_items_table(pr.items || [])}
                    </td>
                </tr>
            `;
        });

        // Add Purchase Invoices
        pi_data.forEach((pi, idx) => {
            let status_color = pi.docstatus === 0 ? '#ff9800' : '#28a745';
            let row_id = `pi-${idx}`;

            // Format date and is_return for display
            let date_display = pi.posting_date ? frappe.datetime.str_to_user(pi.posting_date) : '';
            let additional_info = '';

            if (date_display || pi.is_return || pi.grand_total) {
                let info_parts = [];
                if (date_display) info_parts.push(date_display);
                if (pi.grand_total) info_parts.push(`₹${flt(pi.grand_total, 2)}`);
                if (pi.is_return) info_parts.push('<span style="color: #dc3545; font-weight: 500;">Return</span>');
                additional_info = ` (${info_parts.join(', ')})`;
            }

            html += `
                <tr class="collapsible-row" data-target="${row_id}" style="cursor: pointer;">
                    <td style="text-align: center;">
                        <i class="fa fa-chevron-right expand-icon" style="color: #666;"></i>
                    </td>
                    <td><span style="color: #ff6b35; font-weight: 500;">💰 PI</span></td>
                    <td>
                        <a href="/app/purchase-invoice/${pi.name}" target="_blank" 
                           style="color: #ff6b35; text-decoration: none; font-weight: 500;">${pi.name}</a>
                        <span style="color: #666; font-size: 11px;">${additional_info}</span>
                    </td>
                    <td>
                        <span style="color: ${status_color}; font-weight: 500;">${pi.status}</span>
                    </td>
                </tr>
                <tr id="${row_id}" class="collapsible-content" style="display: none;">
                    <td colspan="4" style="padding: 15px; background: #f9f9f9;">
                        ${build_pi_items_table(pi.items || [], pi.is_return)}
                    </td>
                </tr>
            `;
        });

        // Add Stock Entries
        se_data.forEach((se, idx) => {
            let status_color = se.docstatus === 0 ? '#ff9800' : '#28a745';
            let row_id = `se-${idx}`;

            html += `
                <tr class="collapsible-row" data-target="${row_id}" style="cursor: pointer;">
                    <td style="text-align: center;">
                        <i class="fa fa-chevron-right expand-icon" style="color: #666;"></i>
                    </td>
                    <td><span style="color: #9c27b0; font-weight: 500;">📦 SE</span></td>
                    <td>
                        <a href="/app/stock-entry/${se.name}" target="_blank" 
                           style="color: #9c27b0; text-decoration: none; font-weight: 500;">${se.name}</a>
                    </td>
                    <td>
                        <span style="color: ${status_color}; font-weight: 500;">${se.status}</span>
                    </td>
                </tr>
                <tr id="${row_id}" class="collapsible-content" style="display: none;">
                    <td colspan="4" style="padding: 15px; background: #f9f9f9;">
                        ${build_se_items_table(se.items || [])}
                    </td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;
    }

    html += '</div>';
    return html;
}

// Build Purchase Receipt items table
function build_pr_items_table(items) {
    if (items.length === 0) {
        return '<em style="color: #888;">No items found</em>';
    }

    let html = `
        <table class="table table-sm" style="margin-bottom: 0;">
            <thead>
                <tr style="background: #e3f2fd;">
                    <th>Item Code</th>
                    <th>Item Name</th>
                    <th>Accepted Qty</th>
                    <th>Rejected Qty</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        html += `
            <tr>
                <td><strong>${item.item_code}</strong></td>
                <td>${item.item_name || ''}</td>
                <td><span style="color: #28a745;">${item.accepted_qty}</span></td>
                <td><span style="color: #dc3545;">${item.rejected_qty}</span></td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    return html;
}

// Build Purchase Invoice items table
function build_pi_items_table(items, is_return) {
    if (items.length === 0) {
        return '<em style="color: #888;">No items found</em>';
    }

    let is_return_display = is_return ?
        '<span style="color: #dc3545; font-weight: 500;">Yes</span>' :
        '<span style="color: #28a745;">No</span>';

    let html = `
        <div style="margin-bottom: 10px;">
            <strong>Is Return:</strong> ${is_return_display}
        </div>
        <table class="table table-sm" style="margin-bottom: 0;">
            <thead>
                <tr style="background: #fff3e0;">
                    <th>Item Code</th>
                    <th>Item Name</th>
                    <th>Qty</th>
                    <th>Amount</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        html += `
            <tr>
                <td><strong>${item.item_code}</strong></td>
                <td>${item.item_name || ''}</td>
                <td>${item.qty}</td>
                <td>${frappe.format(item.amount, { fieldtype: 'Currency' })}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    return html;
}

// Build Stock Entry items table
function build_se_items_table(items) {
    if (items.length === 0) {
        return '<em style="color: #888;">No items found</em>';
    }

    let html = `
        <table class="table table-sm" style="margin-bottom: 0;">
            <thead>
                <tr style="background: #f3e5f5;">
                    <th>Item Code</th>
                    <th>Item Name</th>
                    <th>From Warehouse</th>
                    <th>To Warehouse</th>
                    <th>Qty</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        html += `
            <tr>
                <td><strong>${item.item_code}</strong></td>
                <td>${item.item_name || ''}</td>
                <td>${item.from_warehouse || '-'}</td>
                <td>${item.to_warehouse || '-'}</td>
                <td>${item.qty}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    return html;
}

// Setup click handlers for collapsible functionality
function setup_collapsible_handlers() {
    $('.collapsible-row').off('click').on('click', function (e) {
        // Prevent click if clicking on a link
        if ($(e.target).is('a') || $(e.target).closest('a').length) {
            return;
        }

        let target_id = $(this).data('target');
        let content_row = $('#' + target_id);
        let icon = $(this).find('.expand-icon');

        if (content_row.is(':visible')) {
            content_row.hide();
            icon.removeClass('fa-chevron-down').addClass('fa-chevron-right');
        } else {
            content_row.show();
            icon.removeClass('fa-chevron-right').addClass('fa-chevron-down');
        }
    });
}


