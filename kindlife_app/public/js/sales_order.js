// Global flag to prevent infinite loop when applying custom discount
window._applying_custom_discount = false;

frappe.ui.form.on('Sales Order Item', {
    price_list_rate: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
    },
    custom_list_price: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
    },
    item_code: function (frm, cdt, cdn) {
        // Trigger calculation when item is fetched
        // We use a slight delay to allow standard fetch to complete first
        setTimeout(() => {
            let item = locals[cdt][cdn];
            if (item.custom_discount_on === "MRP") {
                apply_custom_discount_logic(frm, cdt, cdn, 'discount_percentage');
            }
        }, 500);
    },
    // Custom discount calculation based on custom_discount_on field
    discount_percentage: function (frm, cdt, cdn) {
        // Prevent infinite loop
        if (window._applying_custom_discount) {
            return;
        }

        let item = locals[cdt][cdn];
        // Only apply custom logic if custom_discount_on is set to "MRP"
        if (item.custom_discount_on !== "MRP") {
            return;
        }

        // Use setTimeout to ensure this runs AFTER the core ERPNext code
        setTimeout(() => {
            apply_custom_discount_logic(frm, cdt, cdn, 'discount_percentage');
        }, 100);
    },
    discount_amount: function (frm, cdt, cdn) {
        // Prevent infinite loop
        if (window._applying_custom_discount) {
            return;
        }

        let item = locals[cdt][cdn];
        // Only apply custom logic if custom_discount_on is set to "MRP"
        if (item.custom_discount_on !== "MRP") {
            return;
        }

        // Use setTimeout to ensure this runs AFTER the core ERPNext code
        setTimeout(() => {
            apply_custom_discount_logic(frm, cdt, cdn, 'discount_amount');
        }, 100);
    },
    custom_discount_on: function (frm, cdt, cdn) {
        let item = locals[cdt][cdn];

        if (item.custom_discount_on === "MRP") {
            // Switching TO MRP — re-run MRP-based discount logic
            if (item.discount_percentage) {
                setTimeout(() => {
                    apply_custom_discount_logic(frm, cdt, cdn, 'discount_percentage');
                }, 100);
            } else if (item.discount_amount) {
                setTimeout(() => {
                    apply_custom_discount_logic(frm, cdt, cdn, 'discount_amount');
                }, 100);
            }
        } else {
            // Switching FROM MRP to Selling Price (or blank) —
            // let ERPNext's standard price_list_rate handler recalculate
            // rate, discount_amount and discount_percentage from price_list_rate.
            setTimeout(() => {
                frm.script_manager.trigger('price_list_rate', cdt, cdn);
            }, 100);
        }
    },
    qty: function (frm, cdt, cdn) {
        let item = locals[cdt][cdn];
        if (item.custom_discount_on !== "MRP") return;

        // Snapshot the user's intent BEFORE the core ERPNext qty chain runs.
        // apply_price_list makes a server call that may:
        //   (a) reset discount_percentage to the Item Price value (Bug 1), and/or
        //   (b) reset custom_discount_on back to "Selling Price" (Bug 2).
        let saved_discount_pct = flt(item.discount_percentage);

        setTimeout(() => {
            let current_item = locals[cdt][cdn];

            // Restore custom_discount_on in case it was reset by apply_price_list
            current_item.custom_discount_on = "MRP";

            // Inject the saved percentage so apply_custom_discount_logic reads it
            current_item.discount_percentage = saved_discount_pct;

            // Re-run full MRP discount logic: recomputes discount_amount,
            // rate, net_amount and totals correctly using the saved % on MRP.
            apply_custom_discount_logic(frm, cdt, cdn, 'discount_percentage');
        }, 800);
    }
});

frappe.ui.form.on('Sales Order', {
    selling_price_list: function (frm) {
        frm.events.update_mrp_based_on_currency(frm);
    },
    refresh: function (frm) {
        update_mrp_label(frm);
        set_custom_type_based_on_role(frm);

        // Display linked documents at the top of the form
        if (frm.doc.docstatus === 1) {
            display_linked_documents(frm);
        }

        // Add standalone buttons FIRST (before ERPNext adds its buttons)
        if (frm.doc.docstatus === 1) {
            // Add standalone Pick List button
            add_pick_list_button(frm);

            // Add Recalculate Margins button
            frm.add_custom_button(__('Recalculate B2C Margins'), function () {
                frappe.call({
                    method: 'kindlife_app.services.margin_engine.recalculate_margins',
                    args: { sales_order_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Recalculating B2C Margins...'),
                    callback: function (r) {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }

        // Remove Pick List and Delivery Note buttons from Create dropdown
        setTimeout(() => {
            if (is_warehouse_only_user()) {
                frm.remove_custom_button('Payment Request', 'Create');
                frm.remove_custom_button('Sales Invoice', 'Create');
                frm.remove_custom_button('Purchase Order', 'Create');
                hide_item_row_edit_icons(frm);
            }
            if (frm.doc.docstatus === 1) {
                frm.remove_custom_button('Pick List', 'Create');
                // frm.remove_custom_button('Delivery Note', 'Create');
                frm.remove_custom_button('Work Order', 'Create');
                frm.remove_custom_button('Request for Raw Materials', 'Create');
                frm.remove_custom_button('Project', 'Create');
            }
        }, 500);
    },
    currency: function (frm) {
        update_mrp_label(frm);
        frm.events.update_mrp_based_on_currency(frm);
        frm.fields_dict.items.grid.refresh();
    },
    conversion_rate: function (frm) {
        frm.fields_dict.items.grid.refresh();
    },
    update_mrp_based_on_currency: function (frm) {
        const rate = frm.doc.conversion_rate || 1;

        frm.doc.items.forEach(item => {
            if (item.custom_mrp_company_currency) {
                console.log("rate", rate);
                console.log("item.custom_mrp_company_currency", item.custom_mrp_company_currency);
                item.custom_list_price = flt(item.custom_mrp_company_currency / rate);
                item.custom_margin = ((item.custom_list_price - item.price_list_rate) / item.custom_list_price) * 100;
            }
        });

        frm.refresh_field('items');
    }
});



function calculate_custom_margin(cdt, cdn) {
    let row = locals[cdt][cdn];
    let custom_list_price = flt(row.custom_list_price);
    let buyer_price = flt(row.price_list_rate);

    if (custom_list_price > 0 && buyer_price > 0) {
        let margin = ((custom_list_price - buyer_price) / custom_list_price) * 100;
        console.log("margin", margin);
        frappe.model.set_value(cdt, cdn, 'custom_margin', flt(margin, 2));
    } else {
        frappe.model.set_value(cdt, cdn, 'custom_margin', null);
    }
}

function update_mrp_label(frm) {
    let currency = frm.doc.currency || "Currency";
    frm.fields_dict["items"].grid.update_docfield_property(
        "custom_list_price", "label", `MRP (${currency})`
    );
}

// Apply custom discount logic based on custom_discount_on field
function apply_custom_discount_logic(frm, cdt, cdn, field) {
    let item = locals[cdt][cdn];

    // Only apply custom logic if custom_discount_on is set to "MRP"
    if (item.custom_discount_on !== "MRP") {
        return; // Let core ERPNext handle the calculation
    }

    // Ensure we have custom_list_price (MRP) to calculate discount on
    if (!item.custom_list_price || item.custom_list_price <= 0) {
        frappe.msgprint(__("Please set MRP (custom_list_price) before applying discount on MRP"));
        return;
    }

    // Set flag to prevent infinite loop
    window._applying_custom_discount = true;

    try {
        // Calculate rate_with_margin (similar to core ERPNext logic)
        let effective_item_rate = item.price_list_rate || 0;
        let rate_with_margin = effective_item_rate;

        if (item.margin_type === "Percentage") {
            rate_with_margin = flt(effective_item_rate) + flt(effective_item_rate) * (flt(item.margin_rate_or_amount) / 100);
        } else if (item.margin_type === "Amount") {
            rate_with_margin = flt(effective_item_rate) + flt(item.margin_rate_or_amount);
        }

        // Store the correct values based on MRP
        let correct_discount_amount;
        let correct_discount_percentage;
        let correct_rate;

        // Now apply discount based on MRP instead of price_list_rate
        if (field === 'discount_percentage') {
            // Calculate discount_amount based on MRP
            // Use item.discount_percentage even if it's 0
            correct_discount_percentage = flt(item.discount_percentage);
            correct_discount_amount = flt(item.custom_list_price) * correct_discount_percentage / 100;

            // Calculate the new rate
            correct_rate = flt(rate_with_margin - correct_discount_amount, precision('rate', item));

        } else if (field === 'discount_amount') {
            // Calculate discount_percentage based on MRP
            // Use item.discount_amount even if it's 0
            correct_discount_amount = flt(item.discount_amount);
            correct_discount_percentage = item.custom_list_price > 0
                ? (100 * correct_discount_amount / flt(item.custom_list_price))
                : 0;

            // Calculate the new rate
            correct_rate = flt(rate_with_margin - correct_discount_amount, precision('rate', item));
        }

        // If correct_rate is not set (shouldn't happen, but safety check)
        if (correct_rate === undefined) {
            correct_rate = rate_with_margin;
            correct_discount_amount = 0;
            correct_discount_percentage = 0;
        }

        // Update the item directly without triggering events
        item.discount_amount = correct_discount_amount;
        item.discount_percentage = correct_discount_percentage;
        item.rate = correct_rate;

        // Refresh the fields in the UI
        frm.refresh_field('items');

        // Trigger recalculation of totals
        frm.script_manager.trigger('rate', cdt, cdn).then(() => {
            // After rate calculation, core ERPNext may have recalculated discount_percentage
            // based on rate_with_margin. We need to restore our MRP-based values.

            // Re-fetch the item to get the latest state
            let updated_item = locals[cdt][cdn];

            // Restore the correct MRP-based discount values
            updated_item.discount_amount = correct_discount_amount;
            updated_item.discount_percentage = correct_discount_percentage;
            updated_item.rate = correct_rate;

            // Recalculate net_amount based on the corrected rate
            updated_item.net_rate = correct_rate;
            updated_item.net_amount = flt(correct_rate * updated_item.qty, precision('net_amount', updated_item));
            updated_item.amount = updated_item.net_amount;

            // Set base amounts
            updated_item.base_rate = flt(correct_rate * frm.doc.conversion_rate, precision('base_rate', updated_item));
            updated_item.base_net_rate = updated_item.base_rate;
            updated_item.base_net_amount = flt(updated_item.net_amount * frm.doc.conversion_rate, precision('base_net_amount', updated_item));
            updated_item.base_amount = updated_item.base_net_amount;

            // Refresh UI to show correct values
            frm.refresh_field('items');

            // Trigger taxes and totals recalculation with the corrected values
            frm.trigger('calculate_taxes_and_totals').then(() => {
                // Reset flag after all calculations are done
                window._applying_custom_discount = false;
            });
        });

    } catch (error) {
        // Reset flag in case of error
        window._applying_custom_discount = false;
        console.error("Error in apply_custom_discount_logic:", error);
        throw error;
    }
}


/**
 * After a qty change, ERPNext's qty() chain recalculates discount_percentage
 * as (1 - rate/price_list_rate)*100  — i.e. on selling price, not MRP.
 * This function restores the correct MRP-based discount_percentage without
 * touching rate or discount_amount (those are already correct).
 */
function restore_mrp_discount_percentage(frm, cdt, cdn) {
    let item = locals[cdt][cdn];
    if (item.custom_discount_on !== "MRP") return;
    if (!item.custom_list_price || item.custom_list_price <= 0) return;

    // Reconstruct rate_with_margin (same logic as apply_custom_discount_logic)
    let effective_item_rate = item.price_list_rate || 0;
    let rate_with_margin = effective_item_rate;
    if (item.margin_type === "Percentage") {
        rate_with_margin = flt(effective_item_rate) + flt(effective_item_rate) * (flt(item.margin_rate_or_amount) / 100);
    } else if (item.margin_type === "Amount") {
        rate_with_margin = flt(effective_item_rate) + flt(item.margin_rate_or_amount);
    }

    // Actual discount amount = rate_with_margin - current rate (correct after core chain)
    let actual_discount_amount = flt(rate_with_margin) - flt(item.rate);

    // Express that discount as a percentage of MRP
    let correct_discount_percentage = flt(
        actual_discount_amount / item.custom_list_price * 100,
        precision('discount_percentage', item)
    );

    if (item.discount_percentage !== correct_discount_percentage) {
        item.discount_percentage = correct_discount_percentage;
        frm.refresh_field('items');
    }
}

// Add standalone Pick List button
function add_pick_list_button(frm) {
    // Check if SO is closed or on hold
    if (frm.doc.status === 'Closed' || frm.doc.status === 'On Hold') return;

    // Check if not fully picked
    if (flt(frm.doc.per_picked) < 100) {
        // Show "Create Pick List" button
        frm.add_custom_button(__('Create Pick List'), function () {
            frappe.model.open_mapped_doc({
                method: "erpnext.selling.doctype.sales_order.sales_order.create_pick_list",
                frm: frm
            });
        });
    }
}

// Display linked Pick Lists and Delivery Notes in tabular format
function display_linked_documents(frm) {
    // Use existing API to fetch linked documents (avoids permission errors)
    frappe.call({
        method: 'kindlife_app.api.sales_order.get_draft_pick_lists_count',
        args: {
            sales_order: frm.doc.name
        },
        callback: function (r) {
            if (r.message) {
                let pl_data = r.message.all_pl_data || [];
                let dn_data = r.message.all_dn_data || [];
                let si_data = r.message.all_si_data || [];

                // Build tabular HTML for linked documents
                let html = build_linked_documents_table_so(pl_data, dn_data, si_data);

                // Set HTML in custom_related_links field
                frm.set_df_property('custom_related_links', 'options', html);
                frm.refresh_field('custom_related_links');

                // Add click handlers for collapsible rows
                setTimeout(() => {
                    setup_collapsible_handlers_so();
                }, 100);
            }
        }
    });
}

// Build the tabular HTML structure with collapsible rows for Sales Order
function build_linked_documents_table_so(pl_data, dn_data, si_data) {
    let html = `
        <div style="margin-bottom: 10px; padding: 12px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #9c27b0;">
            <h5 style="margin-bottom: 15px; color: #9c27b0; font-weight: 600;">📋 Related Documents</h5>
    `;

    // Check if any documents exist
    if (pl_data.length === 0 && dn_data.length === 0 && si_data.length === 0) {
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

        // Add Pick Lists
        pl_data.forEach((pl, idx) => {
            // Use workflow_state if available, otherwise fall back to status
            let display_status = pl.workflow_state || pl.status;

            // Color coding based on workflow states
            let status_color;
            switch (display_status) {
                case 'Draft':
                    status_color = '#6c757d'; // Gray
                    break;
                case 'Sent':
                    status_color = '#17a2b8'; // Teal
                    break;
                case 'for Pickup':
                    status_color = '#ff9800'; // Orange
                    break;
                case 'Items Picked':
                    status_color = '#28a745'; // Green
                    break;
                default:
                    // Fallback to docstatus-based coloring for non-workflow states
                    status_color = pl.docstatus === 0 ? '#ff9800' : '#28a745';
            }

            let row_id = `pl-${idx}`;

            html += `
                <tr class="collapsible-row-so" data-target="${row_id}" style="cursor: pointer;">
                    <td style="text-align: center;">
                        <i class="fa fa-chevron-right expand-icon-so" style="color: #666;"></i>
                    </td>
                    <td><span style="color: #9c27b0; font-weight: 500;">📦 PL</span></td>
                    <td>
                        <a href="/app/pick-list/${pl.name}" target="_blank" 
                           style="color: #9c27b0; text-decoration: none; font-weight: 500;">${pl.name}</a>
                    </td>
                    <td>
                        <span style="color: ${status_color}; font-weight: 500;">${display_status}</span>
                    </td>
                </tr>
                <tr id="${row_id}" class="collapsible-content-so" style="display: none;">
                    <td colspan="4" style="padding: 15px; background: #f9f9f9;">
                        ${build_pl_items_table_so(pl.items || [])}
                    </td>
                </tr>
            `;
        });

        // Add Delivery Notes
        dn_data.forEach((dn, idx) => {
            let status_color = dn.docstatus === 0 ? '#ff9800' : '#28a745';
            let row_id = `dn-${idx}`;

            // Format date and is_return for display
            let date_display = dn.posting_date ? frappe.datetime.str_to_user(dn.posting_date) : '';
            let additional_info = '';

            if (date_display || dn.is_return) {
                let info_parts = [];
                if (date_display) info_parts.push(date_display);
                if (dn.is_return) info_parts.push('<span style="color: #dc3545; font-weight: 500;">Return</span>');
                additional_info = ` (${info_parts.join(', ')})`;
            }

            html += `
                <tr class="collapsible-row-so" data-target="${row_id}" style="cursor: pointer;">
                    <td style="text-align: center;">
                        <i class="fa fa-chevron-right expand-icon-so" style="color: #666;"></i>
                    </td>
                    <td><span style="color: #2490ef; font-weight: 500;">🚚 DN</span></td>
                    <td>
                        <a href="/app/delivery-note/${dn.name}" target="_blank" 
                           style="color: #2490ef; text-decoration: none; font-weight: 500;">${dn.name}</a>
                        <span style="color: #666; font-size: 11px;">${additional_info}</span>
                    </td>
                    <td>
                        <span style="color: ${status_color}; font-weight: 500;">${dn.status}</span>
                    </td>
                </tr>
                <tr id="${row_id}" class="collapsible-content-so" style="display: none;">
                    <td colspan="4" style="padding: 15px; background: #f9f9f9;">
                        ${build_dn_items_table_so(dn.items || [], dn.is_return)}
                    </td>
                </tr>
            `;
        });

        // Add Sales Invoices
        si_data.forEach((si, idx) => {
            let status_color = si.docstatus === 0 ? '#ff9800' : '#28a745';
            let row_id = `si-${idx}`;

            // Format date and is_return for display
            let date_display = si.posting_date ? frappe.datetime.str_to_user(si.posting_date) : '';
            let additional_info = '';

            if (date_display || si.is_return || si.grand_total) {
                let info_parts = [];
                if (date_display) info_parts.push(date_display);
                if (si.grand_total) info_parts.push(`₹${flt(si.grand_total, 2)}`);
                if (si.is_return) info_parts.push('<span style="color: #dc3545; font-weight: 500;">Return</span>');
                additional_info = ` (${info_parts.join(', ')})`;
            }

            html += `
                <tr class="collapsible-row-so" data-target="${row_id}" style="cursor: pointer;">
                    <td style="text-align: center;">
                        <i class="fa fa-chevron-right expand-icon-so" style="color: #666;"></i>
                    </td>
                    <td><span style="color: #28a745; font-weight: 500;">💰 SI</span></td>
                    <td>
                        <a href="/app/sales-invoice/${si.name}" target="_blank" 
                           style="color: #28a745; text-decoration: none; font-weight: 500;">${si.name}</a>
                        <span style="color: #666; font-size: 11px;">${additional_info}</span>
                    </td>
                    <td>
                        <span style="color: ${status_color}; font-weight: 500;">${si.status}</span>
                    </td>
                </tr>
                <tr id="${row_id}" class="collapsible-content-so" style="display: none;">
                    <td colspan="4" style="padding: 15px; background: #f9f9f9;">
                        ${build_si_items_table_so(si.items || [], si.is_return)}
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

// Build Pick List items table
function build_pl_items_table_so(items) {
    if (!items || items.length === 0) {
        return '<p style="color: #888; font-style: italic; margin: 0;">No items found.</p>';
    }

    let table = `
        <table class="table table-sm" style="margin: 0; font-size: 12px;">
            <thead style="background: #e9ecef;">
                <tr>
                    <th>Item</th>
                    <th>Warehouse</th>
                    <th style="text-align: right;">Qty</th>
                    <th style="text-align: right;">Picked Qty</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        table += `
            <tr>
                <td>${item.item_code}</td>
                <td>${item.warehouse || 'N/A'}</td>
                <td style="text-align: right;">${item.qty || 0}</td>
                <td style="text-align: right;">${item.picked_qty || 0}</td>
            </tr>
        `;
    });

    table += `
            </tbody>
        </table>
    `;

    return table;
}

// Build Sales Invoice items table
function build_si_items_table_so(items, is_return) {
    if (!items || items.length === 0) {
        return '<p style="color: #888; font-style: italic; margin: 0;">No items found.</p>';
    }

    let is_return_display = is_return ?
        '<span style="color: #dc3545; font-weight: 500;">Yes</span>' :
        '<span style="color: #28a745;">No</span>';

    let table = `
        <div style="margin-bottom: 10px;">
            <strong>Is Return:</strong> ${is_return_display}
        </div>
        <table class="table table-sm" style="margin: 0; font-size: 12px;">
            <thead style="background: #e9ecef;">
                <tr>
                    <th>Item</th>
                    <th style="text-align: right;">Qty</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        table += `
            <tr>
                <td>${item.item_code}</td>
                <td style="text-align: right;">${item.qty || 0}</td>
            </tr>
        `;
    });

    table += `
            </tbody>
        </table>
    `;

    return table;
}

// Build Delivery Note items table
function build_dn_items_table_so(items, is_return) {
    if (!items || items.length === 0) {
        return '<p style="color: #888; font-style: italic; margin: 0;">No items found.</p>';
    }

    let is_return_display = is_return ?
        '<span style="color: #dc3545; font-weight: 500;">Yes</span>' :
        '<span style="color: #28a745;">No</span>';

    let table = `
        <div style="margin-bottom: 10px;">
            <strong>Is Return:</strong> ${is_return_display}
        </div>
        <table class="table table-sm" style="margin: 0; font-size: 12px;">
            <thead style="background: #e9ecef;">
                <tr>
                    <th>Item</th>
                    <th style="text-align: right;">Qty</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        table += `
            <tr>
                <td>${item.item_code}</td>
                <td style="text-align: right;">${item.qty || 0}</td>
            </tr>
        `;
    });

    table += `
            </tbody>
        </table>
    `;

    return table;
}

// Setup click handlers for collapsible rows in Sales Order
function setup_collapsible_handlers_so() {
    $('.collapsible-row-so').off('click').on('click', function () {
        let target = $(this).data('target');
        let content = $('#' + target);
        let icon = $(this).find('.expand-icon-so');

        if (content.is(':visible')) {
            content.hide();
            icon.removeClass('fa-chevron-down').addClass('fa-chevron-right');
        } else {
            content.show();
            icon.removeClass('fa-chevron-right').addClass('fa-chevron-down');
        }
    });
}