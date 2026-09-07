frappe.ui.form.on('Purchase Receipt', {
  refresh(frm) {

    // This function originally places the "Create" button for quality inspeation
    // Why overload it here instead of direct monkey Patch:
    // Monkey patch will update it globally, we need it to be updated only for PR

    // cscript: It is a object that stores all the functions that might be used in the frontend.
    // So we update the value of setup_quality_inspection to empty so it dont make the button.
    frm.cscript.setup_quality_inspection = function () {
      console.log("Setting up quality inspection");
    }

    setTimeout(() => {
      frm.page.wrapper.find('.inner-group-button[data-label="Create"]').find('a.dropdown-item').filter(function () { return $(this).text().trim() === 'Make Stock Entry'; }).text('Create Putaway')
    }, 0)

    // Set query filter for accepted_warehouse to only show QC warehouses
    frm.set_query('set_warehouse', function () {
      return {
        filters: {
          'custom_is_qc_warehouse': 1
        }
      };
    });

    // Display linked Stock Entries at the top of the form
    if (frm.doc.docstatus === 1) {
      display_linked_stock_entries(frm);
    }

    // Add standalone Create Putaway button FIRST (before ERPNext adds its buttons)
    if (frm.doc.docstatus === 1 && !frm.doc.is_return && frm.doc.status !== 'Closed') {
      add_create_putaway_button(frm);
    }




    setTimeout(() => {
      if (is_warehouse_only_user()) {
        hide_pr_item_row_edit_icons(frm);
      }
      // Remove "Make Stock Entry" from Create dropdown
      frm.remove_custom_button('Make Stock Entry', 'Create');

      frm.remove_custom_button('Purchase Order', 'Get Items From');
      frm.remove_custom_button('Purchase Invoice', 'Get Items From');
      frm.remove_custom_button('Asset', 'View');
      frm.remove_custom_button('Asset Movement', 'View');

      if (is_warehouse_only_user()) {
        frm.remove_custom_button('Accounting Ledger', 'Preview');
        frm.remove_custom_button('Accounting Ledger', 'View');
      }
      if (frm.doc.docstatus === 1) {
        frm.remove_custom_button('Make Stock Entry', 'Create');

        frm.remove_custom_button('Purchase Order', 'Get Items From');
        frm.remove_custom_button('Purchase Invoice', 'Get Items From');

        // Hide finance-related buttons for warehouse-only users
        if (is_warehouse_only_user()) {
          // Remove Landed Cost Voucher button
          frm.remove_custom_button('Landed Cost Voucher', 'Create');

          // Remove Purchase Invoice button
          frm.remove_custom_button('Purchase Invoice', 'Create');
          frm.remove_custom_button('Purchase Invoice');

          // Remove Retention Stock Entry button
          frm.remove_custom_button('Retention Stock Entry', 'Create');
          frm.remove_custom_button('Close', 'Status');


        }
      }
      frm.remove_custom_button('Purchase Return', 'Create');
      frm.add_custom_button(__('Purchase Return'), function () {

        frappe.call({
          method: "kindlife_app.api.purchase_receipt.make_custom_purchase_return",
          args: {
            source_name: frm.doc.name,
          },
          freeze: true,
          freeze_message: __("Creating Return..."),
          callback: function (r) {
            if (r.message) {
              let doc = r.message;
              frappe.model.sync(doc);
              frappe.set_route("Form", doc.doctype, doc.name);
            }
          }
        });

      }, __('Create'));


    }, 500);

    set_custom_type_based_on_role(frm);

    // Add custom "Go To" dropdown button
    add_go_to_dropdown(frm);
    fill_rejected_warehouse(frm);

    // Calling the function to hide the columns
    hide_columns(frm);
    inject_custom_css();
    // Here we set the warehouse mandatory, or hide it depending on if it is return/receipt
    set_warehouse_field_properties(frm);
    if (frm.doc.is_return && frm.doc.return_against && !frm.doc.docstatus) {
      frm.return_scanner = new PurchaseReturnScanner({ frm: frm });
    }

    if (frm.is_new() && frm.doc.is_internal_supplier) {
      set_warehouses_from_delivery_note_js(frm);
    }

  },


  onload: function (frm) {
    // overriding the erpnext function to not show the popup for serial no selection
    erpnext.show_serial_batch_selector = function (frm, item_row, callback, on_close, show_dialog) {
      if (frm.doc.doctype) {
        console.log("Overriden the PR so no Popup for serial no appear here");
        return;
      }

      let warehouse, receiving_stock, existing_stock;

      let warehouse_field = "warehouse";
      if (frm.doc.is_return) {
        if (["Purchase Receipt", "Purchase Invoice"].includes(frm.doc.doctype)) {
          existing_stock = true;
          warehouse = item_row.warehouse;
        } else if (["Delivery Note", "Sales Invoice"].includes(frm.doc.doctype)) {
          receiving_stock = true;
        }
      } else {
        // Bulk auto-fetch undelivered serials for Purchase Receipt returns
        if (frm.doc.doctype == "Stock Entry") {
          if (frm.doc.purpose == "Material Receipt") {
            receiving_stock = true;
          } else {
            existing_stock = true;
            warehouse = item_row.s_warehouse;
          }

          if (in_list([
            "Material Transfer",
            "Send to Subcontractor",
            "Material Issue",
            "Material Consumption for Manufacture",
            "Material Transfer for Manufacture"
          ], frm.doc.purpose)
          ) {
            warehouse_field = "s_warehouse";
          } else {
            warehouse_field = "t_warehouse";
          }
        } else {
          existing_stock = true;
          warehouse = item_row.warehouse;
        }
      }

      if (!warehouse) {
        if (receiving_stock) {
          warehouse = ["like", ""];
        } else if (existing_stock) {
          warehouse = ["!=", ""];
        }
      }

      if (["Sales Invoice", "Delivery Note"].includes(frm.doc.doctype)) {
        item_row.type_of_transaction = frm.doc.is_return ? "Inward" : "Outward";
      } else {
        item_row.type_of_transaction = frm.doc.is_return ? "Outward" : "Inward";
      }

      new erpnext.SerialBatchPackageSelector(frm, item_row, (r) => {
        if (r) {
          let update_values = {
            "serial_and_batch_bundle": r.name,
            "qty": Math.abs(r.total_qty)
          }

          if (r.warehouse) {
            update_values[warehouse_field] = r.warehouse;
          }

          frappe.model.set_value(item_row.doctype, item_row.name, update_values);
        }
      });

    }
  },


  // Run validate in purchase receipt to check if the accepted and rejected qty are toteling to total received quentity
  before_workflow_action: function (frm, action) {
    frm.page.wrapper.toggleClass('hide-qty-and-rejected', false);


    if (frm.selected_workflow_action === "Submit for QC") {
      frm.get_field('items').grid.toggle_enable("custom_received", false);
    }

    if (frm.selected_workflow_action === "Complete QC") {
      return frappe
        .call({
          method: 'kindlife_app.api.pr_validate.verify_pr_sum',
          args: { doc: frm.doc },
          freeze: true,
          freeze_message: __("Validating..."),
        })
        .then(r => { })
        .catch(err => {
          frappe.dom.unfreeze();
          throw new Error("Validation failed");
        });
    }


  },

  validate: function (frm) {
    validate_serial_counts(frm);
  },
  custom_scan_barcodes: function (frm) {
    if (frm.return_scanner) {
      frm.return_scanner.process_scan(frm.doc.custom_scan_barcodes);
    }
  },

  custom_fetch_all_items: function (frm) {
    if (frm.doc.custom_fetch_all_items && frm.return_scanner) {
      frm.return_scanner.fill_all_tables();
    }
  }


});

function set_warehouses_from_delivery_note_js(frm) {
  let delivery_note = frm.doc.inter_company_reference;
  // if (frm.doc.items && frm.doc.items.length > 0) {
  //   for (let item of frm.doc.items) {
  //     if (item.delivery_note) {
  //       delivery_note = item.delivery_note;
  //       break;
  //     }
  //   }
  // }
  console.log(delivery_note);
  if (!delivery_note) return;

  frappe.call({
    method: 'kindlife_app.api.purchase_receipt.get_warehouses_from_delivery_note',
    args: { delivery_note: delivery_note },
    callback: function (r) {
      if (r.message) {
        let wh = r.message;

        let fields_to_set = {};

        if (wh.set_from_warehouse) fields_to_set.set_from_warehouse = wh.set_from_warehouse;
        if (wh.set_warehouse) fields_to_set.set_warehouse = wh.set_warehouse;
        if (wh.rejected_warehouse) fields_to_set.rejected_warehouse = wh.rejected_warehouse;

        if (Object.keys(fields_to_set).length > 0) {
          frm.set_value(fields_to_set);
        }

        // Cascade to children
        frm.doc.items.forEach(item => {
          let item_fields = {};
          if (wh.set_from_warehouse) item_fields.from_warehouse = wh.set_from_warehouse;
          if (wh.set_warehouse) item_fields.warehouse = wh.set_warehouse;
          if (wh.rejected_warehouse) item_fields.rejected_warehouse = wh.rejected_warehouse;

          // Use base qty for custom_received initializing
          if (item.qty > 0 && !item.custom_received) {
            item_fields.custom_received = item.qty;

            // Clear qty so user has to fill it, but use setTimeout to run after standard Frappe mappings
            setTimeout(() => {
              frappe.model.set_value(item.doctype, item.name, 'qty', 0);
            }, 500);
          }

          if (Object.keys(item_fields).length > 0) {
            frappe.model.set_value(item.doctype, item.name, item_fields);
          }
        });
      }
    }
  });
}



function inject_custom_css() {
  // Check if style already exists to prevent duplicate insertion on refresh
  if ($('#custom-pr-css').length > 0) return;

  const css = `
        .always-hide-in_pr .grid-static-col[data-fieldname="custom_total_returnable_qty"],
        .always-hide-in_pr .grid-static-col[data-fieldname="warehouse"]{
          display: none !important;
          width: 0 !important;
          padding: 0 !important;
        }


        .hide-qty-and-rejected .grid-static-col[data-fieldname="qty"],
        .hide-qty-and-rejected .grid-static-col[data-fieldname="custom_rejection_reason"],
        .hide-qty-and-rejected .grid-static-col[data-fieldname="batch_no"],
        .hide-qty-and-rejected .grid-static-col[data-fieldname="custom_ean"],
        .hide-qty-and-rejected .grid-static-col[data-fieldname="rejected_qty"]{
          display: none !important;
          width: 0 !important;
          padding: 0 !important;
          }
          
        .pr-return-hide-fields .grid-static-col[data-fieldname="custom_received"],
        .pr-return-hide-fields .grid-static-col[data-fieldname="custom_rejection_reason"],
        .pr-return-hide-fields .grid-static-col[data-fieldname="rejected_qty"]{
          display: none !important;
          width: 0 !important;
          padding: 0 !important;
        }
    `;

  $('<style id="custom-pr-css">')
    .prop('type', 'text/css')
    .html(css)
    .appendTo('head');
}






// Function responsible for hiding the columns according to workflow state/purchase receipr/return
function hide_columns(frm) {
  frm.page.wrapper.toggleClass('hide-qty-and-rejected', false);
  frm.page.wrapper.toggleClass('pr-return-hide-fields', false);

  if (frm.doc.is_return) {
    frm.set_df_property('custom_related_links', 'hidden', 1);

    frm.page.wrapper.toggleClass('always-hide-in_pr', false);
    frm.page.wrapper.toggleClass('pr-return-hide-fields', true);
    frm.set_df_property('items', 'reqd', 0, frm.doc.name, 'custom_rejection_reason');
  }
  else if (frm.doc.is_internal_supplier) {
    // For internal suppliers, we DO want to show qty/rejected_qty even on Draft, 
    // because internal transfers don't go through the external QC workflow in the same way.
    frm.page.wrapper.toggleClass('always-hide-in_pr', true);
    frm.page.wrapper.toggleClass('hide-qty-and-rejected', false);
  }
  else {
    frm.page.wrapper.toggleClass('always-hide-in_pr', true);
    if (frm.is_new() || frm.doc.workflow_state === "Draft") {
      frm.page.wrapper.toggleClass('hide-qty-and-rejected', true);
    }
  }
}

frappe.ui.form.on('Purchase Receipt Item', {
  item_code: function (frm, cdt, cdn) {
    setTimeout(() => {
      if (is_warehouse_only_user()) {
        hide_pr_item_row_edit_icons(frm);
      }
    }, 100);
  },
  batch_no(frm, cdt, cdn) {
    check_remaining_life(frm, cdt, cdn)
  },
  // When the user adds the rejected qty check, it will atomatically fill the accepted qty field.
  rejected_qty: function (frm, cdt, cdn) {
    console.log("rejected_qty called");

    let row = locals[cdt][cdn];
    // Do not add autofill logic for return PR as in that case, the max value for qty and rej qty is checked with the value of corresponding column in PR, so if there sum will be equal or less than received qty, not always equal to it
    if (frm.doc.is_return) { return; }

    // Auto-calculating accepted qty
    let received = row.custom_received || 0;

    // If it's an internal supplier, use original qty if custom_received is empty, 
    // but the user wants custom_received to work. Let's ensure custom_received is set or used.
    frappe.model.set_value(cdt, cdn, 'qty', received - row.rejected_qty);
    frm.set_df_property(
      "items",                            // fieldname of the child table on the parent
      'reqd',                             // property name
      row.rejected_qty > 0,               // condition
      frm.doc.name,                       // parent docname
      "custom_rejection_reason",          // fieldname inside the child
      cdn                                 // the child row name
    );
  },

  // Also auto-calculate when custom_received changes
  custom_received: function (frm, cdt, cdn) {
    if (frm.doc.is_return) { return; }
    let row = locals[cdt][cdn];
    let rejected = row.rejected_qty || 0;
    frappe.model.set_value(cdt, cdn, 'qty', row.custom_received - rejected);
  }

});



async function check_remaining_life(frm, cdt, cdn) {
  // Get particular row for which batch no is changed
  const row = frappe.get_doc(cdt, cdn);
  if (!row.batch_no) return;

  try {
    // Fetch manuf date and shelf life
    const [batchRes, itemRes] = await Promise.all([
      frappe.db.get_value('Batch', row.batch_no, ['manufacturing_date', 'expiry_date']),
      frappe.db.get_value('Item', row.item, 'shelf_life_in_days')
    ]);

    const mfg = batchRes.message.manufacturing_date;
    const exp = batchRes.message.expiry_date;
    const shelf_life = itemRes.message.shelf_life_in_days;
    const shelf = frappe.datetime.get_day_diff(exp, mfg)

    console.log('MFG:', mfg, ' Shelf Life:', shelf, ' exp:', exp);

    const time_left = frappe.datetime.get_day_diff(exp, frm.doc.posting_date);
    const min_limit = shelf * 0.75;

    console.log('Time left:', time_left, ' Minimum limit:', min_limit);
    console.log("frm", frm.doc.posting_date);

    if (time_left < min_limit) {
      frappe.model.set_value(cdt, cdn, 'custom_rejection_reason', 'The item has less than 75% life left');
      frappe.model.set_value(cdt, cdn, 'rejected_qty', row.custom_received);
      frappe.model.set_value(cdt, cdn, 'qty', 0);
      frappe.msgprint({
        title: __('Shelf-Life Warning'),
        message: __('Batch {0} has less than 75% shelf-life remaining.', [
          row.batch_no, row.item
        ]),
        indicator: 'orange'
      });

    }
    else {
      if (row.custom_rejection_reason == "The item has less than 75% life left") {
        frappe.model.set_value(cdt, cdn, 'custom_rejection_reason', '');
        frappe.model.set_value(cdt, cdn, 'rejected_qty', 0);
        frappe.model.set_value(cdt, cdn, 'qty', row.custom_received);
      }
    }

  } catch (err) {
    console.error('Shelf life check error:', err);
  }
}



function fill_rejected_warehouse(frm) {
  //  Add new wareouse of the doctype is new
  // If making purchase return, dont make rejection reason compulsory
  if (frm.is_new() && !frm.doc.is_return) {
    frappe.call({
      method: 'frappe.client.get_value',
      args: {
        doctype: 'Warehouse',
        filters: { 'is_rejected_warehouse': 1 },
        fieldname: 'name'
      },
      callback: (r) => {
        if (r.message && r.message.name) {
          // console.log(r.message);

          frm.set_value('rejected_warehouse', r.message.name);
        }
      }
    });
  }

}

// Add standalone Create Putaway button - simplified version
function add_create_putaway_button(frm) {
  // Check if all items have been put away by comparing received qty with transferred qty
  frappe.call({
    method: 'kindlife_app.api.purchase_receipt.get_draft_stock_entries_count',
    args: {
      purchase_receipt: frm.doc.name
    },
    callback: function (r) {
      if (r.message) {
        let se_data = r.message.all_se_data || [];
        let transferred_qty = r.message.transferred_qty || {};

        // Check if there are any submitted Stock Entries
        let has_submitted_se = se_data.some(se => se.docstatus === 1);

        // If there are submitted Stock Entries, check if all items are transferred
        if (has_submitted_se) {
          // Check if all PR items have been fully transferred
          let all_transferred = true;
          (frm.doc.items || []).forEach(item => {
            let transferred = transferred_qty[item.item_code] || 0;
            if (transferred < item.qty) {
              all_transferred = false;
            }
          });

          // Only show button if not all items are transferred
          if (!all_transferred) {
            frm.add_custom_button(__('Create Putaway'), function () {
              frappe.model.open_mapped_doc({
                method: "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_stock_entry",
                frm: frm
              });
            }).addClass('btn-primary');
          }
        } else {
          // No submitted Stock Entries yet, show the button
          frm.add_custom_button(__('Create Putaway'), function () {
            frappe.model.open_mapped_doc({
              method: "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_stock_entry",
              frm: frm
            });
          }).addClass('btn-primary');
        }
      }
    }
  });
}

// Display linked Stock Entries at the top of the form
function display_linked_stock_entries(frm) {
  // Use existing API to fetch linked Stock Entries (avoids permission errors)
  frappe.call({
    method: 'kindlife_app.api.purchase_receipt.get_draft_stock_entries_count',
    args: {
      purchase_receipt: frm.doc.name
    },
    callback: function (r) {
      if (r.message) {
        let se_data = r.message.all_se_data || [];

        // Build HTML for linked Stock Entries
        let html = '<div style="margin-bottom: 10px; padding: 12px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #9c27b0;">';

        if (se_data.length > 0) {
          html += '<div>';
          html += '<strong style="color: #9c27b0; font-size: 14px;">📦 Stock Entries (Putaway):</strong> ';
          se_data.forEach((se, idx) => {
            if (idx > 0) html += ', ';
            let status_color = se.docstatus === 0 ? '#ff9800' : '#28a745';
            let status_text = se.docstatus === 0 ? 'Draft' : 'Submitted';
            html += `<a href="/app/stock-entry/${se.name}" target="_blank" style="color: #9c27b0; text-decoration: none; font-weight: 500;">${se.name}</a>`;
            html += ` <span style="color: ${status_color}; font-size: 12px;">(${status_text})</span>`;
          });
          html += '</div>';
        } else {
          html += '<span style="color: #888; font-style: italic;">No Stock Entries created yet.</span>';
        }

        html += '</div>';

        // Set HTML in custom_related_links field
        frm.set_df_property('custom_related_links', 'options', html);
        frm.refresh_field('custom_related_links');
      }
    }
  });
}

// Add custom "Go To" dropdown button
function add_go_to_dropdown(frm) {
  // Only show if document is saved (not new)
  if (frm.is_new()) return;

  // Get the first item to check for linked Purchase Order
  if (frm.doc.items && frm.doc.items.length > 0) {
    let first_item = frm.doc.items[0];

    // Check if there's a linked Purchase Order
    if (first_item.purchase_order) {
      // Add "Go To" dropdown button
      frm.add_custom_button(__('Purchase Order'), function () {
        // Redirect to the linked Purchase Order
        frappe.set_route('Form', 'Purchase Order', first_item.purchase_order);
      }, __('Go To'));

      // Style the dropdown button
      setTimeout(() => {
        // Find the "Go To" dropdown and style it
        let go_to_btn = frm.page.btn_secondary.find('[data-label="Go%20To"]').parent();
        if (go_to_btn.length) {
          go_to_btn.addClass('btn-info');

          // Add icon to the button
          let btn_text = go_to_btn.find('.hidden-xs');
          if (btn_text.length && !btn_text.find('i').length) {
            btn_text.prepend('<i class="fa fa-external-link" style="margin-right: 5px;"></i>');
          }
        }
      }, 100);
    }
  }
}

// Hide row edit icons in Purchase Receipt Item table for warehouse-only users
function hide_pr_item_row_edit_icons(frm) {
  // Hide edit icons in the items child table
  if (frm.fields_dict.items && frm.fields_dict.items.grid) {
    // Override each grid row's toggle_view method
    frm.fields_dict.items.grid.grid_rows.forEach(function (grid_row) {
      if (grid_row && grid_row.toggle_view) {
        // Store original toggle_view method
        if (!grid_row.original_toggle_view) {
          grid_row.original_toggle_view = grid_row.toggle_view;
        }

        // Override toggle_view to do nothing for warehouse users
        grid_row.toggle_view = function () {
          if (is_warehouse_only_user()) {
            // Do nothing - prevent row expansion
            return false;
          } else {
            // Call original method for non-warehouse users
            return this.original_toggle_view.apply(this, arguments);
          }
        };
      }
    });

    // Hide the edit button for each row
    frm.fields_dict.items.grid.wrapper.find('.grid-row .btn-open-row').hide();

    // Also hide the edit icon that appears on row hover
    frm.fields_dict.items.grid.wrapper.find('.grid-row .grid-row-open').hide();

    // Override grid's setup_allow_bulk_edit method to prevent row interactions
    if (!frm.fields_dict.items.grid.original_setup_allow_bulk_edit) {
      frm.fields_dict.items.grid.original_setup_allow_bulk_edit = frm.fields_dict.items.grid.setup_allow_bulk_edit;

      frm.fields_dict.items.grid.setup_allow_bulk_edit = function () {
        if (!is_warehouse_only_user()) {
          return this.original_setup_allow_bulk_edit.apply(this, arguments);
        }
        // For warehouse users, don't setup bulk edit (prevents row interactions)
      };
    }

    // Enable pointer events only for editable fields for warehouse users
    if (is_warehouse_only_user()) {
      // Disable pointer events on the entire row
      frm.fields_dict.items.grid.wrapper.find('.grid-row').css({
        'pointer-events': 'none',
        'cursor': 'default'
      });

      // Re-enable pointer events for specific editable fields
      let editable_fields = ['qty', 'rejected_qty', 'custom_rejection_reason', 'batch_no'];
      editable_fields.forEach(function (fieldname) {
        frm.fields_dict.items.grid.wrapper.find(`[data-fieldname="${fieldname}"]`).css({
          'pointer-events': 'auto',
          'cursor': 'text'
        });
      });
    }

    // Add CSS to hide edit icons and enable specific fields for warehouse users
    if (!$('#warehouse-user-hide-pr-edit-icons').length) {
      let warehouseUserCSS = '';
      if (is_warehouse_only_user()) {
        warehouseUserCSS = `
          .frappe-control[data-fieldname="items"] .grid-row {
            pointer-events: none !important;
            cursor: default !important;
          }
          .frappe-control[data-fieldname="items"] .grid-row:hover {
            background-color: inherit !important;
          }
          .frappe-control[data-fieldname="items"] .grid-row [data-fieldname="qty"],
          .frappe-control[data-fieldname="items"] .grid-row [data-fieldname="rejected_qty"],
          .frappe-control[data-fieldname="items"] .grid-row [data-fieldname="custom_rejection_reason"],
          .frappe-control[data-fieldname="items"] .grid-row [data-fieldname="batch_no"] {
            pointer-events: auto !important;
            cursor: text !important;
          }
        `;
      }

      $('<style id="warehouse-user-hide-pr-edit-icons">')
        .text(`
          .grid-row .btn-open-row,
          .grid-row .grid-row-open,
          .grid-row .grid-row-check:hover + .grid-row-open {
            display: none !important;
          }
          ${warehouseUserCSS}
        `)
        .appendTo('head');
    }

    // Override the grid's make_row method to apply restrictions to new rows
    if (!frm.fields_dict.items.grid.original_make_row) {
      frm.fields_dict.items.grid.original_make_row = frm.fields_dict.items.grid.make_row;

      frm.fields_dict.items.grid.make_row = function (doc, idx, columns) {
        // Call original make_row
        var row = this.original_make_row.apply(this, arguments);

        // Apply restrictions to the new row if warehouse user
        if (is_warehouse_only_user() && row && row.toggle_view) {
          if (!row.original_toggle_view) {
            row.original_toggle_view = row.toggle_view;
          }

          row.toggle_view = function () {
            return false; // Prevent row expansion
          };
        }

        return row;
      };
    }

    // Apply field-level restrictions for warehouse users
    if (is_warehouse_only_user()) {
      setTimeout(() => {
        apply_field_restrictions(frm);
      }, 200);
    }
  }
}

// Apply field-level restrictions for warehouse users
function apply_field_restrictions(frm) {
  if (!is_warehouse_only_user()) return;

  let editable_fields = ['qty', 'rejected_qty', 'custom_rejection_reason', 'batch_no'];

  // Disable non-editable fields by making them non-interactive
  frm.fields_dict.items.grid.wrapper.find('.grid-row').each(function () {
    let row = $(this);

    // Find all field controls in this row
    row.find('[data-fieldname]').each(function () {
      let field_wrapper = $(this);
      let fieldname = field_wrapper.attr('data-fieldname');

      if (!editable_fields.includes(fieldname)) {
        // Make non-editable fields visually disabled and non-interactive
        field_wrapper.find('input, select, textarea').prop('readonly', true).css({
          'background-color': '#f8f9fa',
          'color': '#6c757d',
          'cursor': 'not-allowed'
        });

        // Disable pointer events for non-editable fields
        field_wrapper.css('pointer-events', 'none');
      } else {
        // Ensure editable fields are interactive
        field_wrapper.find('input, select, textarea').prop('readonly', false).css({
          'background-color': '',
          'color': '',
          'cursor': 'text'
        });

        // Enable pointer events for editable fields
        field_wrapper.css('pointer-events', 'auto');
      }
    });
  });
}

function set_warehouse_field_properties(frm) {
  if (frm.doc.is_return) {
    frm.set_df_property('set_warehouse', 'reqd', 0);
    frm.set_df_property('set_warehouse', 'hidden', 1);
    frm.set_df_property('rejected_warehouse', 'hidden', 1);
  } else {
    frm.set_df_property('set_warehouse', 'hidden', 0);
    frm.set_df_property('', 'hidden', 0);
    frm.set_df_property('set_warehouse', 'reqd', 1);
  }
}




/*
  This function checks if the number of serial numers is strictly equal to the number of returned items
*/

function validate_serial_counts(frm) {
  if (!frm.doc.is_return) {
    return true;
  }
  let error_data = [];

  // 1. Loop through all items to find mismatches
  frm.doc.items.forEach(item => {

    // Helper: Count non-empty lines
    const get_count = (str) => {
      if (!str) return 0;
      return str.split('\n').filter(s => s.trim() !== '').length;
    };

    let acc_count = get_count(item.serial_no);
    let rej_count = get_count(item.rejected_serial_no);

    let acc_qty = Math.abs(item.qty);
    let rej_qty = Math.abs(item.rejected_qty);

    let has_acc_error = false;
    let has_rej_error = false;

    // Check Accepted Mismatch
    // If field has text OR qty > 0, they must match.
    if (acc_count !== acc_qty) { has_acc_error = true; }

    // Check Rejected Mismatch
    if (rej_count !== rej_qty) { has_rej_error = true; }

    // Only add to list if there is at least one error
    if (has_acc_error || has_rej_error) {
      error_data.push({
        idx: item.idx,
        item_code: item.item_code,
        acc_qty: has_acc_error ? acc_qty : '',
        acc_count: has_acc_error ? acc_count : '',
        rej_qty: has_rej_error ? rej_qty : '',
        rej_count: has_rej_error ? rej_count : ''
      });
    }
  });

  // 2. If errors exist, build the table
  if (error_data.length > 0) {
    frappe.validated = false; // Stop the save

    let table_rows = error_data.map(d => `
            <tr>
                <td class="text-center">${d.idx}</td>
                <td>${d.item_code}</td>
                <td class="text-center text-danger"><b>${d.acc_qty}</b></td>
                <td class="text-center text-danger">${d.acc_count}</td>
                <td class="text-center text-danger"><b>${d.rej_qty}</b></td>
                <td class="text-center text-danger">${d.rej_count}</td>
            </tr>
        `).join('');

    let error_html = `
            <p>The number of Serial Numbers provided does not match the Quantity for the following items:</p>
            <table class="table table-bordered table-condensed table-hover" style="margin-top:10px;">
                <thead>
                    <tr class="active">
                        <th class="text-center" width="10%">Row</th>
                        <th width="30%">Item</th>
                        <th class="text-center" width="15%">Acc Qty</th>
                        <th class="text-center" width="15%">Acc Serials</th>
                        <th class="text-center" width="15%">Rej Qty</th>
                        <th class="text-center" width="15%">Rej Serials</th>
                    </tr>
                </thead>
                <tbody>
                    ${table_rows}
                </tbody>
            </table>
            <p class="text-muted small">* Fields are left blank where the count is correct.</p>
        `;

    frappe.msgprint({
      title: __('Validation Error'),
      message: error_html,
      indicator: 'red',
      wide: true
    });
  }
}



class PurchaseReturnScanner {
  constructor(opts) {
    this.frm = opts.frm;
    this.cache = { groups: {}, scan_map: {} };
    this.init_data();
  }

  init_data() {
    // Fetch ALL data (Groups + Map) and store in JS memory
    frappe.call({
      method: "kindlife_app.api.purchase_receipt.get_return_context",
      args: { pr_name: this.frm.doc.return_against },
      freeze: true,
      callback: (r) => {
        if (r.message) {
          this.cache = r.message;
        }
      }
    });
  }

  process_scan(barcode) {
    this.frm.set_value("custom_scan_barcodes", "");
    console.log("Barcode : ", barcode);
    if (!barcode) return;
    console.log("Barcode : ", barcode);

    // 1. Lookup in Map
    const match_data = this.cache.scan_map[barcode];

    if (!match_data) {
      frappe.throw(__("Barcode <b>{0}</b> is invalid.", [barcode]));
      return;
    }

    const group_key = match_data.key;
    const resolved_serial = match_data.serial;

    // 2. FETCH GROUP DATA (Missing Step Fix)
    // We need this data to recreate the row if it's missing
    const group_data = this.cache.groups[group_key];
    console.log("group_data  -->  ", group_data);

    if (!group_data) {
      frappe.throw(__("Data missing for this group key. Please refresh."));
      return;
    }

    // 3. Find or Create Row
    let row = this.get_table_row(group_key);

    if (!row) {
      // RECREATION LOGIC: User deleted the row, bring it back
      // Now 'group_data' is defined, so this will work
      row = this.create_row_from_cache(group_data);
    }

    // 4. Update Row
    this.add_serial_to_row(row, resolved_serial, group_data);
  }

  get_table_row(key) {
    console.log("Key : ", key);

    const [item, wh, batch, pr_row_name] = key.split("::");
    return (this.frm.doc.items || []).find(r =>
      r.item_code === item &&
      r.warehouse === wh &&
      r.batch_no === batch &&
      r.purchase_receipt_item === pr_row_name
    );
  }

  create_row_from_cache(data) {
    let row = this.frm.add_child('items');
    // Copy Static Data from Cache
    row.item_code = data.item_code;
    row.item_name = data.item_name;
    row.warehouse = data.warehouse;
    row.batch_no = data.batch_no;
    row.purchase_receipt_item = data.pr_item_name;
    row.rate = data.rate;
    row.uom = data.uom;
    row.stock_uom = data.stock_uom;
    row.conversion_factor = data.conversion_factor;
    row.custom_total_returnable_qty = data.serials.length;
    row.return_qty_from_rejected_warehouse = data.is_rejected_origin ? 1 : 0;

    // Init empty
    row.qty = 0;
    row.rejected_qty = 0;
    row.serial_no = "";

    return row;
  }

  add_serial_to_row(row, serial, group_data) {
    // 1. Validation: Duplicate in Row
    let current_serials = row.serial_no ? row.serial_no.split('\n') : [];
    if (current_serials.includes(serial)) {
      frappe.show_alert({ message: __("Serial already scanned"), indicator: 'red' });
      return;
    }

    // 2. Update
    current_serials.push(serial);
    row.serial_no = current_serials.join('\n');

    // Update Quantities
    row.qty = -1 * current_serials.length;
    row.received_qty = row.qty;
    row.stock_qty = row.qty * (row.conversion_factor || 1);
    row.use_serial_batch_fields = 1;

    this.frm.refresh_field('items');
    frappe.show_alert({ message: __("Added {0}", [serial]), indicator: 'green' });
  }

  fill_all_tables() {
    frappe.dom.freeze("Filling all returnable items ...");

    // 1. Clear Table
    this.frm.clear_table('items');

    // 2. Iterate Cache and Build Rows
    // cache.groups contains EVERYTHING (Rejected & Accepted)
    for (let key in this.cache.groups) {
      let data = this.cache.groups[key];

      // Create Row
      let row = this.create_row_from_cache(data);

      // Fill All Serials
      row.serial_no = data.serials.join('\n');

      // Set Qty
      row.qty = -1 * data.serials.length;
      row.received_qty = row.qty;
      row.stock_qty = row.qty * (row.conversion_factor || 1);
      row.use_serial_batch_fields = 1;
    }

    this.frm.refresh_field('items');
    frappe.dom.unfreeze();
    frappe.msgprint({ title: "Success", message: "All returnable items filled.", indicator: "green" });
  }
}
