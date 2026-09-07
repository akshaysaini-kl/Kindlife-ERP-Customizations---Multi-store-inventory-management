// Global flag to prevent infinite loop when applying custom discount
window._applying_custom_discount_si = false;

frappe.ui.form.on('Sales Invoice Item', {
    price_list_rate: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
    },
    custom_list_price: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
        calculate_custom_amount_with_gst(cdt, cdn);
    },
    qty: function (frm, cdt, cdn) {
        calculate_custom_amount_with_gst(cdt, cdn);
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

            // Inject the saved percentage so apply_custom_discount_logic_si reads it
            current_item.discount_percentage = saved_discount_pct;

            // Re-run full MRP discount logic: recomputes discount_amount,
            // rate, net_amount and totals correctly using the saved % on MRP.
            apply_custom_discount_logic_si(frm, cdt, cdn, 'discount_percentage');
        }, 800);
    },
    custom_margin: function (frm, cdt, cdn) {
        calculate_custom_amount_with_gst(cdt, cdn);
    },
    // Custom discount calculation based on custom_discount_on field
    discount_percentage: function (frm, cdt, cdn) {
        // Prevent infinite loop
        if (window._applying_custom_discount_si) {
            return;
        }

        let item = locals[cdt][cdn];
        // Only apply custom logic if custom_discount_on is set to "MRP"
        if (item.custom_discount_on !== "MRP") {
            return;
        }

        // Use setTimeout to ensure this runs AFTER the core ERPNext code
        setTimeout(() => {
            apply_custom_discount_logic_si(frm, cdt, cdn, 'discount_percentage');
        }, 100);
    },
    discount_amount: function (frm, cdt, cdn) {
        // Prevent infinite loop
        if (window._applying_custom_discount_si) {
            return;
        }

        let item = locals[cdt][cdn];
        // Only apply custom logic if custom_discount_on is set to "MRP"
        if (item.custom_discount_on !== "MRP") {
            return;
        }

        // Use setTimeout to ensure this runs AFTER the core ERPNext code
        setTimeout(() => {
            apply_custom_discount_logic_si(frm, cdt, cdn, 'discount_amount');
        }, 100);
    },
    custom_discount_on: function (frm, cdt, cdn) {
        let item = locals[cdt][cdn];

        if (item.custom_discount_on === "MRP") {
            // Switching TO MRP — re-run MRP-based discount logic
            if (item.discount_percentage) {
                setTimeout(() => {
                    apply_custom_discount_logic_si(frm, cdt, cdn, 'discount_percentage');
                }, 100);
            } else if (item.discount_amount) {
                setTimeout(() => {
                    apply_custom_discount_logic_si(frm, cdt, cdn, 'discount_amount');
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
    }
});

frappe.ui.form.on('Sales Invoice', {
    selling_price_list: function (frm) {
        frm.events.update_mrp_based_on_currency(frm);
    },
    refresh: function (frm) {
        update_mrp_label(frm);
        set_custom_type_based_on_role(frm);
        setTimeout(() => {
            frm.remove_custom_button('Delivery', 'Create');
            
        }, 100);

    },
    currency: function (frm) {
        update_mrp_label(frm);
        frm.events.update_mrp_based_on_currency(frm);
        frm.fields_dict.items.grid.refresh();
    },
    conversion_rate: function (frm) {//I couldnt find this field in SI or SO; but this was added to the code of SO so i m ot removing it from here, if not required, will remove after review
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
    },

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

function calculate_custom_amount_with_gst(cdt, cdn) {
    let row = locals[cdt][cdn];
    let custom_list_price = flt(row.custom_list_price);
    let qty = flt(row.qty);
    let custom_margin = flt(row.custom_margin);

    // Formula: (custom_list_price * qty) * (1 - custom_margin/100)
    let amount = (custom_list_price * qty) * (1 - (custom_margin / 100));
    frappe.model.set_value(cdt, cdn, 'custom_amount_with_gst', flt(amount, 2));
    
    // Update header total
    calculate_header_total_with_gst(cur_frm);
}

function calculate_header_total_with_gst(frm) {
    let total = 0;
    (frm.doc.items || []).forEach(item => {
        total += flt(item.custom_amount_with_gst);
    });
    frm.set_value('custom_total_with_gst', flt(total, 2));
}

function update_mrp_label(frm) {
    let currency = frm.doc.currency || "Currency";
    frm.fields_dict["items"].grid.update_docfield_property(
        "custom_list_price", "label", `MRP (${currency})`
    );
}

// Apply custom discount logic based on custom_discount_on field for Sales Invoice
function apply_custom_discount_logic_si(frm, cdt, cdn, field) {
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
    window._applying_custom_discount_si = true;

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
                window._applying_custom_discount_si = false;
            });
        });

    } catch (error) {
        // Reset flag in case of error
        window._applying_custom_discount_si = false;
        console.error("Error in apply_custom_discount_logic_si:", error);
        throw error;
    }
}

/**
 * After a qty change, ERPNext's qty() chain recalculates discount_percentage
 * as (1 - rate/price_list_rate)*100  — i.e. on selling price, not MRP.
 * This function restores the correct MRP-based discount_percentage without
 * touching rate or discount_amount (those are already correct).
 */
function restore_mrp_discount_percentage_si(frm, cdt, cdn) {
    let item = locals[cdt][cdn];
    if (item.custom_discount_on !== "MRP") return;
    if (!item.custom_list_price || item.custom_list_price <= 0) return;

    // Reconstruct rate_with_margin (same logic as apply_custom_discount_logic_si)
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