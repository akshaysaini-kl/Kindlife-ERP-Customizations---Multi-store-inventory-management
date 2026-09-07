frappe.ui.form.on('Delivery Note', {
    refresh: function (frm) {
        // Add Go To dropdown button
        add_go_to_dropdown_dn(frm);
        add_download_shipment_button(frm);
        set_custom_type_based_on_role(frm);

        setTimeout(() => {
            if (is_warehouse_only_user()) {
                // Hide Close button from Status dropdown
                frm.remove_custom_button('Close', 'Status');
                // frm.remove_custom_button('Sales Return', 'Create');
                frm.remove_custom_button('Sales Invoice', 'Create');

                // Hide Accounting Ledger from View dropdown
                frm.remove_custom_button('Accounting Ledger', 'View');
                frm.remove_custom_button('Accounting Ledger', 'Preview');
                frm.remove_custom_button('Stock Ledger', 'Preview');
                frm.remove_custom_button('Sales Order', 'Get Items From');
                frm.remove_custom_button('Pick List', 'Get Items From');
            }
        }, 500);
        // hide_columns(frm)
        hide_columns(frm)

    },
    shipping_address_name: function(frm) {
        if (!frm.doc.shipping_address_name) {
            frm.set_value("set_target_warehouse", null);
            return;
        }

        frappe.call({
            method: "kindlife_app.custom_scripts.delivery_note.get_warehouses_from_address",
            args: {
                address: frm.doc.shipping_address_name
            },
            callback: function(r) {
                if (r.message && r.message.transit_warehouse) {
                    frm.set_value("set_target_warehouse", r.message.transit_warehouse);
                } else {
                    frm.set_value("set_target_warehouse", null);
                }
            }
        });
    }
});

// Add Go To dropdown button for Delivery Note
function add_go_to_dropdown_dn(frm) {
    // Get the first Delivery Note item to find the Sales Order and Pick List
    if (!frm.doc.items || frm.doc.items.length === 0) {
        return;
    }

    // Find the first item with sales order or pick list
    const first_item = frm.doc.items[0];
    const sales_order = first_item.against_sales_order;
    const pick_list = first_item.against_pick_list;

    // Only add dropdown if we have at least one reference
    if (!sales_order && !pick_list) {
        return;
    }



    // Add Sales Order option if available
    if (sales_order) {
        frm.add_custom_button(__('Sales Order'), function () {
            frappe.set_route('Form', 'Sales Order', sales_order);
        }, __('Go To'));
    }

    // Add Pick List option if available
    if (pick_list) {
        frm.add_custom_button(__('Pick List'), function () {
            frappe.set_route('Form', 'Pick List', pick_list);
        }, __('Go To'));
    }
}

function add_download_shipment_button(frm) {
    frm.add_custom_button(__('Download Shipment PDF'), function() {
        // 1. Fetch data from the first item
        const first_item = (frm.doc.items || [])[0];
        const shipment_id = first_item ? first_item.custom_shipment_id : null;
        const awb_number = first_item ? first_item.custom_awb_number : null;

        if (!shipment_id) {
            frappe.msgprint(__('Shipment ID not found on Delivery Note items.'));
            return;
        }

        frappe.show_alert({
            message: __('Shipment ID: {0}, AWB: {1}', [shipment_id, awb_number]),
            indicator: 'blue'
        });

        /*
        // 3. Call the future API (to be implemented by another developer)
        frappe.call({
            method: 'kindlife_app.api.shipment.download_shipment_pdf',
            args: {
                shipment_id: shipment_id,
                awb_number: awb_number
            },
            callback: function(r) {
                if (r.message && r.message.pdf_base64) {
                    const base64PDF = r.message.pdf_base64;
                    
                    // Open PDF in a new window
                    const pdfWindow = window.open("");
                    pdfWindow.document.write(
                        `<title>Shipment ${shipment_id}</title>` +
                        `<iframe width='100%' height='100%' src='data:application/pdf;base64,${base64PDF}'></iframe>`
                    );
                } else if (r.message && r.message.error) {
                    frappe.msgprint(__('API Error: {0}', [r.message.error]));
                }
            }
        });
        */

        // Temporary placeholder till real API is added
        frappe.msgprint({
            title: __('Shipment PDF Integration'),
            indicator: 'blue',
            message: `
                <p>${__('This button will trigger the Shipment API once finalized.')}</p>
                <div style="background-color: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 10px;">
                    <b>${__('Data to be sent:')}</b><br>
                    ${__('Shipment ID')}: <code>${shipment_id}</code><br>
                    ${__('AWB Number')}: <code>${awb_number || '<i>Not Set</i>'}</code>
                </div>
            `
        });
    }, __('Actions'));
}


function hide_columns(frm) {
    inject_custom_css();
    if (!frm.doc.is_return) {
        hide = true
        frm.page.wrapper.toggleClass('dn-hide-for-non-return', hide);
        return;
    }
    else if (frm.doc.is_return) {
        hide = false
        frm.page.wrapper.toggleClass('dn-hide-for-non-return', hide);
        return;
    }

}



function inject_custom_css() {
    // Check if style already exists to prevent duplicate insertion on refresh
    if ($('#custom-dn-css').length > 0) return;
    const css = `
        .dn-hide-for-non-return .grid-static-col[data-fieldname="custom_damage_qty"],
        .dn-hide-for-non-return .grid-static-col[data-fieldname="custom_return_remarks"]{            
            display: none !important;
            width: 0 !important;
            padding: 0 !important;
        }
    `;

    $('<style id="custom-dn-css">')
        .prop('type', 'text/css')
        .html(css)
        .appendTo('head');
}
