// Define this at the top of your file, outside of the frappe.ui.form.on block
frappe.trigger_barcode_api = function(event, child_docname, parent_docname) {
    // 1. THE SILVER BULLET: Kill the event immediately.
    // This stops it from reaching the grid row and opening the modal.
    if (event) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
    }

    const frm = cur_frm;
    const row = frappe.get_doc("Stock Entry Detail", child_docname);

    if (frm.is_dirty()) {
        frappe.msgprint({
            title: __('Unsaved Changes'),
            message: __('Please save the document before generating barcodes.'),
            indicator: 'orange'
        });
        return;
    }

    if (!row.serial_no && !row.serial_and_batch_bundle) {
        frappe.msgprint({
            title: __('No Serial Data'),
            message: __('No serial numbers or Serial/Batch Bundle found on this row.'),
            indicator: 'orange'
        });
        return;
    }

    frappe.show_alert({
        message: __('Generating barcodes...'),
        indicator: 'blue'
    });

    frappe.call({
        method: 'kindlife_app.api.barcode_download.download_row_barcodes',
        args: {
            stock_entry_name: frm.doc.name,
            row_name: child_docname
        },
        freeze: true,
        freeze_message: __('Generating Barcode PDF...'),
        callback: function (r) {
            if (r.message && r.message.pdf_base64) {
                const byteCharacters = atob(r.message.pdf_base64);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                const blob = new Blob([byteArray], { type: 'application/pdf' });
                const url = URL.createObjectURL(blob);
                const printWindow = window.open(url, '_blank');
                if (printWindow) {
                    printWindow.addEventListener('load', function() {
                        printWindow.print();
                    });
                }
                frappe.show_alert({
                    message: __('Barcodes generated successfully'),
                    indicator: 'green'
                });
            }
        }
    });
};

frappe.ui.form.on('Stock Entry', {
    onload: function (frm) {
        // Initialize the custom serial scanner
        if (!frm.serial_scanner) {
            frm.serial_scanner = new StockEntrySerialScanner({
                frm: frm
            });
        }
    },
    check_scanning_status(frm) {
        if (!frm.doc.items || frm.doc.items.length === 0) return;

        let all_scanned = frm.doc.items.every(row => row.custom_scanned_qty == row.qty);

        if (all_scanned) {
            frm.dashboard.clear_headline();
            frm.dashboard.set_headline(
                __("<span style='color:green; font-weight:600;'>✔ Scanning Completed</span>")
            );
        } else {
            frm.dashboard.clear_headline();
        }
    },
    custom_skip_barcode_scanning(frm) {
        if (frm.doc.custom_skip_barcode_scanning) {
            // loop through all items and set scanned qty = qty
            (frm.doc.items || []).forEach(row => {
                // First remove the existing values of the custom_scanned_serial_no field
                frappe.model.set_value(row.doctype, row.name, "custom_scanned_serial_no", "");
                
                // Copy all values of serial_no field to custom_scanned_serial_no field if present
                if (row.serial_no) {
                    frappe.model.set_value(row.doctype, row.name, "custom_scanned_serial_no", row.serial_no);
                }

                frappe.model.set_value(row.doctype, row.name, "custom_scanned_qty", row.qty);
            });

            frm.refresh_field("items");
            frm.trigger("check_scanning_status");
            frappe.msgprint(__("All scanned quantities and serials set equal to Qty and Serial No."));
        }
    },
    setup(frm) {
        apply_barcode_meta_formatter(frm);
        setup_barcode_row_handlers(frm);
    },
    refresh(frm) {
        apply_barcode_meta_formatter(frm);
        setup_barcode_row_handlers(frm);
        set_warehouse_in_se(frm);
        set_custom_type_based_on_role(frm);

        setTimeout(() => {
            frm.remove_custom_button('Material Request', 'Create');
            frm.remove_custom_button('Purchase Invoice', 'Get Items From');
            frm.remove_custom_button('Material Request', 'Get Items From');
            frm.remove_custom_button('Bill of Materials', 'Get Items From');
            frm.remove_custom_button('Transit Entry', 'Get Items From');
            frm.remove_custom_button('Accounting Ledger', 'View');
        }, 500);

        // Add custom "Go To" dropdown button
        add_go_to_dropdown_se(frm);

        // Add button for new putaway rule popup
        frm.add_custom_button(__('New Putaway Rule'), () => {
            frappe.ui.form.make_quick_entry(
                'Putaway Rule',
                (doc) => {
                    frappe.show_alert({
                        message: __(`Putaway Rule ${doc.name} created successfully. Re-applying rules...`),
                        indicator: 'green'
                    }, 5);

                    if (frm.doc.items && frm.doc.items.length > 0) {
                        frappe.call({
                            method: "erpnext.stock.doctype.putaway_rule.putaway_rule.apply_putaway_rule",
                            args: {
                                doctype: frm.doc.doctype,
                                items: frm.doc.items,
                                company: frm.doc.company,
                                purpose: frm.doc.purpose,
                                sync: true
                            },
                            callback: (r) => {
                                frm.set_value('items', r.message);
                            }
                        })
                    }
                }
            )
        });

        frm.trigger("check_scanning_status");

        // Ensure serial scanning buttons are re-added on refresh (persistence after save)
        if (frm.serial_scanner) {
            frm.serial_scanner.add_scanning_buttons();
        }
    },
    custom_scan_serial_no: function (frm) {
        if (frm.doc.custom_scan_serial_no && frm.serial_scanner) {
            frm.serial_scanner.process_serial_scan(frm.doc.custom_scan_serial_no);
        }
    }
});

frappe.ui.form.on("Stock Entry Detail", {
    custom_scanned_qty(frm, cdt, cdn) {
        frm.fields_dict["items"].grid.refresh();
        frm.trigger("check_scanning_status");
    },
    serial_and_batch_bundle(frm, cdt, cdn) {
        // Real-time sync: when a bundle is added/changed, refresh scanner data
        if (frm.serial_scanner) {
            frm.serial_scanner.load_local_serial_data();
        }
    }
});

class StockEntrySerialScanner {
    constructor(opts) {
        this.frm = opts.frm;
        this.scan_field_name = "custom_scan_serial_no";
        this.scanned_qty_field = "custom_scanned_qty";
        this.scanned_serial_field = "custom_scanned_serial_no";

        // Cache for all serial data
        this.serial_cache = new Map(); // serial_no -> {serial_no, item_code, item_idx, batch_no, warehouse}
        this.row_serials = new Map();  // item_idx -> [serial_nos]
        this.item_serials = new Map(); // item_code -> [serial_nos]

        // Sound options
        this.success_sound = "submit";
        this.fail_sound = "error";

        // Add custom CSS for formatting
        this.add_custom_css();

        // Initialize Row Locking Mixin
        Object.assign(this, RowLockingMixin);
        this.initRowLocking({
            frm: this.frm,
            child_table_field: 'items'
        });

        // Initialize scanner
        this.setup_scanner();
        // Buttons will be added via refresh trigger to ensure persistence
    }

    add_custom_css() {
        if (!$('#serial-scanner-css').length) {
            $('head').append(`
              <style id="serial-scanner-css">
                  .scanned-complete {
                      animation: pulse-green 0.6s ease-in-out;
                  }
                  
                  .scanned-partial {
                      animation: pulse-orange 0.4s ease-in-out;
                  }
                  
                  @keyframes pulse-green {
                      0% { transform: scale(1); }
                      50% { transform: scale(1.05); background-color: #28a745; color: white; }
                      100% { transform: scale(1); }
                  }
                  
                  @keyframes pulse-orange {
                      0% { transform: scale(1); }
                      50% { transform: scale(1.03); background-color: #f39c12; color: white; }
                      100% { transform: scale(1); }
                  }
                  
                  .scan-complete-icon {
                      animation: bounce-in 0.5s ease-out;
                  }
                  
                  @keyframes bounce-in {
                      0% { transform: scale(0); opacity: 0; }
                      60% { transform: scale(1.2); opacity: 1; }
                      100% { transform: scale(1); opacity: 1; }
                  }
                  
                  .scanned-complete:hover {
                      background-color: #c3e6cb !important;
                      transform: scale(1.02);
                      transition: all 0.2s ease;
                  }
                  
                  .scanned-partial:hover {
                      background-color: #ffeaa7 !important;
                      transform: scale(1.02);
                      transition: all 0.2s ease;
                  }
                  
                  .serial-progress-indicator {
                      display: inline-block;
                      margin-left: 5px;
                      font-size: 0.8em;
                      padding: 1px 4px;
                      border-radius: 10px;
                      font-weight: bold;
                  }
              </style>
          `);
        }
    }

    async setup_scanner() {
        // Load serial data from form items (local + bundle API)
        await this.load_local_serial_data();
        
        this.frm.refresh_field('items');
    }

    /**
     * Load serial data from both frm.doc.items (text) and Serial/Batch Bundles (API).
     */
    async load_local_serial_data() {
        this.serial_cache.clear();
        this.row_serials.clear();
        this.item_serials.clear();

        if (!this.frm.doc.items) return;

        // Check if any row has a bundle
        const bundles_to_fetch = this.frm.doc.items
            .filter(item => item.serial_and_batch_bundle)
            .map(item => item.serial_and_batch_bundle);

        let bundle_data = {};
        if (bundles_to_fetch.length > 0) {
            const response = await frappe.call({
                method: "kindlife_app.custom_scripts.stock_entry.get_bundle_serial_data",
                args: { stock_entry_name: this.frm.doc.name }
            });
            bundle_data = response.message || {};
        }

        this.frm.doc.items.forEach(item => {
            let serials_with_batch = [];

            // 1. Get from serial_no text field
            if (item.serial_no) {
                const sn_list = item.serial_no.split('\n').map(s => s.trim()).filter(s => s);
                sn_list.forEach(sn => {
                    serials_with_batch.push({ serial_no: sn, batch_no: item.batch_no });
                });
            }

            // 2. Get from bundle data
            if (item.serial_and_batch_bundle && bundle_data[item.serial_and_batch_bundle]) {
                serials_with_batch = serials_with_batch.concat(bundle_data[item.serial_and_batch_bundle]);
            }

            serials_with_batch.forEach(entry => {
                const sn = entry.serial_no;
                if (!sn) return;

                this.serial_cache.set(sn, {
                    serial_no: sn,
                    item_code: item.item_code,
                    item_idx: item.idx,
                    batch_no: entry.batch_no,
                    warehouse: item.t_warehouse
                });

                // Group by row idx
                if (!this.row_serials.has(item.idx)) {
                    this.row_serials.set(item.idx, []);
                }
                this.row_serials.get(item.idx).push(sn);

                // Group by item code
                if (!this.item_serials.has(item.item_code)) {
                    this.item_serials.set(item.item_code, []);
                }
                this.item_serials.get(item.item_code).push(sn);
            });
        });

        if (this.serial_cache.size > 0) {
            console.log(`Loaded ${this.serial_cache.size} serial numbers from text and bundles`);
        }
    }

    add_scanning_buttons() {
        // Validate All Scanned Serials
        this.frm.add_custom_button(__('Validate All Scanned Serials'), async () => {
            await this.validate_all_scanned_serials();
        }, __('Serial Scanning'));

        // Clear All Scanned Data (Only for Draft)
        if (this.frm.doc.docstatus === 0) {
            this.frm.add_custom_button(__('Clear All Scanned Data'), () => {
                this.clear_all_scanned_data();
            }, __('Serial Scanning'));
        }

        // Show Scanning Progress
        this.frm.add_custom_button(__('Show Scanning Progress'), async () => {
            await this.show_scanning_progress();
        }, __('Serial Scanning'));

        // Reload Serial Data (re-parses form items)
        this.frm.add_custom_button(__('Reload Serial Data'), async () => {
            await this.load_local_serial_data();
            this.show_alert(__("Serial data reloaded from form and bundles"), "green");
        }, __('Serial Scanning'));

        // Add Row Locking buttons from mixin
        if (!this.frm.is_new()) {
            this.add_row_locking_buttons();
        }
    }

    async process_serial_scan(scanned_value) {
        try {
            // Clear the scan field immediately
            this.frm.set_value(this.scan_field_name, "");

            if (!scanned_value) return;

            // Reload cache if empty
            if (this.serial_cache.size === 0) {
                await this.load_local_serial_data();
            }

            // Lookup in cache
            const serial_data = this.serial_cache.get(scanned_value);

            if (!serial_data) {
                this.show_alert(__("Serial number not found: {0}", [scanned_value]), "red");
                this.play_fail_sound();
                return;
            }

            // Find the correct row
            const target_idx = this.find_appropriate_row(serial_data);

            if (!target_idx) {
                this.show_alert(__("No matching row found for serial {0}", [scanned_value]), "orange");
                this.play_fail_sound();
                return;
            }

            const row = this.frm.doc.items.find(item => item.idx === target_idx);
            if (!row) {
                this.show_alert(__("Row not found"), "red");
                this.play_fail_sound();
                return;
            }

            // ============================================
            // ROW LOCKING CHECK (NEW)
            // ============================================
            
            // Check if row is locked by another user
            if (this.is_row_locked_by_other(target_idx)) {
                const lock_data = this.locked_rows.get(target_idx);
                this.show_alert(
                    __("Row #{0} is being scanned by {1}", [target_idx, lock_data.user_full_name]),
                    "orange",
                    5
                );
                this.play_fail_sound();
                return;
            }
            
            // Try to acquire lock if not already locked by current user
            const existing_lock = this.locked_rows.get(target_idx);
            const is_my_lock = existing_lock && existing_lock.user === frappe.session.user;
            
            if (!is_my_lock) {
                // Need to acquire lock
                const lock_acquired = await this.try_lock_row(target_idx, row.item_code);
                
                if (!lock_acquired) {
                    // Lock acquisition failed (another user grabbed it)
                    this.play_fail_sound();
                    return;
                }
            }
            
            // ============================================
            // END ROW LOCKING CHECK
            // ============================================

            // Validate serial is in this row's serial list
            const valid_serials = this.row_serials.get(row.idx) || [];
            if (!valid_serials.includes(serial_data.serial_no)) {
                this.show_alert(__("Serial {0} does not belong to Row #{1}", [serial_data.serial_no, row.idx]), "red");
                this.play_fail_sound();
                return;
            }

            // Check if already scanned
            if (this.is_already_scanned(row, serial_data.serial_no)) {
                this.show_alert(__("Serial {0} already scanned", [serial_data.serial_no]), "orange");
                this.play_fail_sound();
                return;
            }

            // Add to scanned serials
            await this.add_scanned_serial(row, serial_data.serial_no);

            this.show_alert(__("Row #{0}: Serial {1} scanned ✓", [row.idx, serial_data.serial_no]), "green");
            this.play_success_sound();

        } catch (error) {
            console.error("Error processing serial scan:", error);
            this.show_alert(__("Error: {0}", [error.message]), "red");
            this.play_fail_sound();
        }
    }

    find_appropriate_row(serial_data) {
        for (let item of this.frm.doc.items) {
            // Match item code
            if (item.item_code === serial_data.item_code) {
                // Match warehouse (t_warehouse for target warehouse)
                if (item.t_warehouse && serial_data.warehouse && item.t_warehouse !== serial_data.warehouse) {
                    continue; // Skip if warehouse doesn't match 
                }
                
                // Check if serial belongs to this row
                const valid_serials = this.row_serials.get(item.idx) || [];
                if (valid_serials.includes(serial_data.serial_no)) {
                    return item.idx;
                }
            }
        }
        return null;
    }

    is_already_scanned(row, serial_no) {
        const scanned_serials = row[this.scanned_serial_field] || "";
        const serial_list = scanned_serials.split('\n').filter(s => s.trim());
        return serial_list.includes(serial_no);
    }

    async add_scanned_serial(row, serial_no) {
        const current_scanned = row[this.scanned_serial_field] || "";
        const current_qty = row[this.scanned_qty_field] || 0;

        const new_scanned_serials = current_scanned ?
            current_scanned + '\n' + serial_no :
            serial_no;

        await frappe.model.set_value(row.doctype, row.name, this.scanned_serial_field, new_scanned_serials);
        await frappe.model.set_value(row.doctype, row.name, this.scanned_qty_field, current_qty + 1);

        this.frm.refresh_field('items');
    }

    async validate_all_scanned_serials() {
        // Reload cache to ensure fresh data
        await this.load_local_serial_data();

        const validation_results = [];

        for (let item of this.frm.doc.items) {
            if (!item[this.scanned_serial_field]) continue;

            const scanned_serials = item[this.scanned_serial_field].split('\n').filter(s => s.trim());
            const row_serial_list = this.row_serials.get(item.idx) || [];

            const item_result = {
                item_code: item.item_code,
                idx: item.idx,
                valid_serials: [],
                invalid_serials: [],
                missing_serials: [...row_serial_list]
            };

            scanned_serials.forEach(serial => {
                if (row_serial_list.includes(serial)) {
                    item_result.valid_serials.push(serial);
                    const missing_index = item_result.missing_serials.indexOf(serial);
                    if (missing_index > -1) {
                        item_result.missing_serials.splice(missing_index, 1);
                    }
                } else {
                    item_result.invalid_serials.push(serial);
                }
            });

            validation_results.push(item_result);
        }

        this.display_validation_results(validation_results);
    }

    display_validation_results(results) {
        let html = '<div class="validation-results">';

        results.forEach(item => {
            html += `<div class="item-validation" style="margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">`;
            html += `<h5>Row #${item.idx}: ${item.item_code}</h5>`;

            if (item.valid_serials.length > 0) {
                html += `<p><strong style="color: green;">✅ Valid (${item.valid_serials.length}):</strong><br>`;
                html += `<small>${item.valid_serials.join(', ')}</small></p>`;
            }

            if (item.invalid_serials.length > 0) {
                html += `<p><strong style="color: red;">❌ Invalid (${item.invalid_serials.length}):</strong><br>`;
                html += `<small>${item.invalid_serials.join(', ')}</small></p>`;
            }

            if (item.missing_serials.length > 0) {
                html += `<p><strong style="color: orange;">⏳ Missing (${item.missing_serials.length}):</strong><br>`;
                html += `<small>${item.missing_serials.slice(0, 10).join(', ')}${item.missing_serials.length > 10 ? '...' : ''}</small></p>`;
            }

            html += `</div>`;
        });

        html += '</div>';

        frappe.msgprint({
            title: __('Serial Validation Results'),
            message: html,
            wide: true
        });
    }

       clear_all_scanned_data() {
        const items_to_clear = (this.frm.doc.items || []).filter(item => (item[this.scanned_qty_field] || 0) > 0);

        if (items_to_clear.length === 0) {
            frappe.msgprint(__('No scanned data found to clear.'));
            return;
        }

        // Build HTML table with row locking integration
        let html = `
            <div style="max-height: 400px; overflow-y: auto;">
                <table class="table table-bordered table-condensed" style="margin-bottom: 0;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="width: 40px; text-align: center;">
                                <input type="checkbox" id="select-all-clear" style="cursor: pointer;">
                            </th>
                            <th>${__('Item Code')}</th>
                            <th>${__('Warehouse')}</th>
                            <th class="text-right" style="width: 100px;">${__('Scanned')}</th>
                            <th style="width: 120px;">${__('Status')}</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        items_to_clear.forEach(item => {
            // Check if row is locked
            const lock_data = this.locked_rows.get(item.idx);
            const is_locked_by_me = lock_data && lock_data.user === frappe.session.user;
            const is_locked_by_other = lock_data && lock_data.user !== frappe.session.user;
            
            // Determine if checkbox should be disabled
            const is_disabled = is_locked_by_other;
            const row_class = is_locked_by_other ? 'table-warning' : (is_locked_by_me ? 'table-info' : '');
            
            // Status badge
            let status_badge = '';
            if (is_locked_by_me) {
                status_badge = '<span class="badge badge-info">🔓 Your Lock</span>';
            } else if (is_locked_by_other) {
                status_badge = `<span class="badge badge-warning" title="Locked by ${lock_data.user_full_name}">🔒 ${lock_data.user_full_name}</span>`;
            } else {
                status_badge = '<span class="badge badge-secondary">Unlocked</span>';
            }
            
            html += `
                <tr class="${row_class}">
                    <td style="text-align: center;">
                        <input type="checkbox" 
                               class="clear-item-checkbox" 
                               data-name="${item.name}" 
                               data-idx="${item.idx}"
                               ${is_disabled ? 'disabled' : ''}
                               style="cursor: ${is_disabled ? 'not-allowed' : 'pointer'};">
                    </td>
                    <td>
                        <div style="font-weight: 500;">${item.item_code}</div>
                        <small class="text-muted">Row #${item.idx}</small>
                    </td>
                    <td>${item.t_warehouse || '<em class="text-muted">Not Set</em>'}</td>
                    <td class="text-right">
                        <span class="badge ${item[this.scanned_qty_field] == item.qty ? 'badge-success' : 'badge-warning'}">
                            ${item[this.scanned_qty_field]} / ${item.qty}
                        </span>
                    </td>
                    <td>${status_badge}</td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
            <div style="margin-top: 10px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
                <small>
                    <strong>ℹ️ Note:</strong> You can only clear rows that are not locked by other users.<br>
                    🔓 = Your locked rows | 🔒 = Locked by others | Unlocked = Available to clear
                </small>
            </div>
        `;

        const d = new frappe.ui.Dialog({
            title: __('Selective Clear Scanned Data'),
            fields: [
                {
                    label: __('Select items to reset scanning progress:'),
                    fieldname: 'items_html',
                    fieldtype: 'HTML',
                    options: html
                }
            ],
            primary_action_label: __('Clear Selected'),
            primary_action: () => {
                const selected_names = [];
                d.$wrapper.find('.clear-item-checkbox:checked:not(:disabled)').each(function() {
                    selected_names.push($(this).data('name'));
                });

                if (selected_names.length === 0) {
                    frappe.msgprint(__('Please select at least one item to clear.'));
                    return;
                }

                // Track which rows were cleared (by idx)
                const cleared_row_indices = [];
                
                selected_names.forEach(name => {
                    const item = this.frm.doc.items.find(i => i.name === name);
                    if (item) {
                        // Clear scanned data
                        frappe.model.set_value(item.doctype, item.name, this.scanned_serial_field, '');
                        frappe.model.set_value(item.doctype, item.name, this.scanned_qty_field, 0);
                        
                        // Track cleared row index
                        cleared_row_indices.push(item.idx);
                    }
                });

                // Store cleared row indices in document flags (no DB change needed)
                if (!this.frm.doc.__cleared_rows) {
                    this.frm.doc.__cleared_rows = [];
                }
                this.frm.doc.__cleared_rows = this.frm.doc.__cleared_rows.concat(cleared_row_indices);

                this.frm.refresh_field('items');
                this.show_alert(__('{0} rows cleared successfully', [selected_names.length]), 'blue');
                d.hide();
                
                // Also trigger scanning status check
                this.frm.trigger("check_scanning_status");
            }
        });

        d.show();

        // Handle "Select All" checkbox - only select unlocked rows
        d.$wrapper.find('#select-all-clear').on('change', function() {
            const checked = $(this).prop('checked');
            d.$wrapper.find('.clear-item-checkbox:not(:disabled)').prop('checked', checked);
        });
    }


    async show_scanning_progress() {
        // Reload cache for accurate data
        await this.load_local_serial_data();

        let progress_html = '<div class="scanning-progress">';
        let total_required_qty = 0;
        let total_scanned_qty = 0;

        this.frm.doc.items.forEach(item => {
            const row_serial_list = this.row_serials.get(item.idx) || [];
            const required_qty = row_serial_list.length;
            const scanned_qty = item[this.scanned_qty_field] || 0;

            total_required_qty += required_qty;
            total_scanned_qty += scanned_qty;

            let percentage = required_qty > 0 ? (scanned_qty / required_qty * 100).toFixed(1) : 0;
            let color = percentage == 100 ? '#28a745' : percentage > 0 ? '#ffc107' : '#dc3545';
            let icon = percentage == 100 ? '✅' : percentage > 0 ? '⏳' : '❌';

            progress_html += `
              <div class="progress-item" style="margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                  <strong>${icon} Row #${item.idx}: ${item.item_code}</strong><br>
                  <div style="background: #f0f0f0; border-radius: 10px; margin: 8px 0; height: 20px; overflow: hidden;">
                      <div style="background: ${color}; width: ${percentage}%; height: 100%; border-radius: 10px; transition: width 0.3s ease;"></div>
                  </div>
                  <small><strong>${scanned_qty}/${required_qty}</strong> serials scanned (${percentage}%)</small>
                  ${percentage == 100 ? '<span style="color: green; margin-left: 10px;">✅ Complete</span>' : ''}
              </div>
          `;
        });

        let overall_percentage = total_required_qty > 0 ? (total_scanned_qty / total_required_qty * 100).toFixed(1) : 0;
        let overall_color = overall_percentage == 100 ? '#28a745' : overall_percentage > 0 ? '#17a2b8' : '#dc3545';

        progress_html = `
          <div style="margin-bottom: 25px; padding: 15px; background: linear-gradient(135deg, #f8f9fa, #e9ecef); border-radius: 10px; border-left: 5px solid ${overall_color};">
              <h4 style="margin-bottom: 10px;">📊 Overall Progress: ${overall_percentage}%</h4>
              <div style="background: #e9ecef; border-radius: 15px; height: 30px; overflow: hidden;">
                  <div style="background: linear-gradient(90deg, ${overall_color}, ${overall_color}aa); width: ${overall_percentage}%; height: 100%; border-radius: 15px; transition: width 0.5s ease;"></div>
              </div>
              <div style="margin-top: 10px; display: flex; justify-content: space-between;">
                  <small><strong>${total_scanned_qty}/${total_required_qty}</strong> total serials scanned</small>
                  <small>${this.frm.doc.items.length} items total</small>
              </div>
          </div>
      ` + progress_html + '</div>';

        frappe.msgprint({
            title: __('📈 Scanning Progress Report'),
            message: progress_html,
            wide: true
        });
    }

    show_alert(message, indicator, duration = 3) {
        frappe.show_alert({
            message: message,
            indicator: indicator
        }, duration);
    }

    play_success_sound() {
        if (this.success_sound) {
            frappe.utils.play_sound(this.success_sound);
        }
    }

    play_fail_sound() {
        if (this.fail_sound) {
            frappe.utils.play_sound(this.fail_sound);
        }
    }
}

// Add custom "Go To" dropdown button for Stock Entry
function add_go_to_dropdown_se(frm) {
    if (frm.is_new()) return;

    if (frm.doc.items && frm.doc.items.length > 0) {
        let first_item = frm.doc.items[0];

        if (first_item.reference_purchase_receipt) {
            frm.add_custom_button(__('Purchase Receipt'), function () {
                frappe.set_route('Form', 'Purchase Receipt', first_item.reference_purchase_receipt);
            }, __('Go To'));

            frappe.call({
                method: 'kindlife_app.api.stock_entry.get_purchase_order_from_receipt',
                args: {
                    purchase_receipt: first_item.reference_purchase_receipt,
                    item_code: first_item.item_code
                },
                callback: function (r) {
                    if (r.message && r.message.purchase_order) {
                        frm.add_custom_button(__('Purchase Order'), function () {
                            frappe.set_route('Form', 'Purchase Order', r.message.purchase_order);
                        }, __('Go To'));
                    }
                }
            });
        }
    }
}

/**
 * Write the barcode button formatter onto frappe.meta (the authoritative source).
 * Must be called with the current frm so doc.name is always fresh.
 * Handles both the generate-button field and the file-link field.
 */

// Function to set t_warehouse query based on parent's custom_type
/**
 * Writes formatters onto frappe.meta.docfield_map['Stock Entry Detail'].
 * No inline onclick — click handling is done via setup_barcode_row_handlers.
 */
/**
 * Sets formatters on frappe.meta.docfield_map['Stock Entry Detail'] — the global
 * singleton. Every render path reads from here (directly for user_defined_columns,
 * or via _apply_custom_formatter for per-row copies that lack df.formatter).
 *
 * CRITICAL: _apply_custom_formatter (formatters.js:31) calls the formatter with
 * only (value, df) — doc is NEVER passed. Any formatter that reads doc.xxx will
 * throw TypeError and abort setup_columns(), preventing grid-row-render from firing.
 * For custom_generate_barcode we need no doc at all — the CDN is read from the
 * native .grid-row[data-name] attribute in the capture-phase click handler.
 */
function apply_barcode_meta_formatter(frm) {
    const map = frappe.meta.docfield_map && frappe.meta.docfield_map['Stock Entry Detail'];
    if (!map) return;

    // The Robust Formatter for the Barcode Button
    const barcode_formatter = function (value, df, options, doc) {
        return `<span class="kl-barcode-btn text-primary font-weight-bold"
                      style="cursor: pointer; text-decoration: underline; user-select: none;">
                    ${__("BARCODES")}
                </span>`;
    };

    // 1. Triple-Threat Injection for 'custom_generate_barcodes' (Global Meta Map)
    if (map['custom_generate_barcodes']) {
        map['custom_generate_barcodes'].formatter = barcode_formatter;
    }

    // Direct Grid Injection (if frm is provided)
    if (frm && frm.fields_dict.items && frm.fields_dict.items.grid) {
        const grid = frm.fields_dict.items.grid;
        const fieldname = 'custom_generate_barcodes';

        // 2. Grid Fields Map override (for internal state)
        if (grid.fields_map && grid.fields_map[fieldname]) {
            grid.fields_map[fieldname].formatter = barcode_formatter;
        }
        
        // Final Force: refresh with a small delay to ensure we beat Frappe's internal caching
        setTimeout(() => {
            if (grid.grid_rows) {
                grid.grid_rows.forEach(row => {
                    row.refresh_field(fieldname);
                });
            }
        }, 300);
    }

    // Scanned Qty formatting (Keep existing)
    if (map['custom_scanned_qty']) {
        map['custom_scanned_qty'].formatter = function (value, df, options, doc) {
            if (doc && value == doc.qty) {
                return `<div style="background-color: #d4edda; color: #155724; font-weight: 600; text-align: center; width: 100%; height: 100%; padding: 3px 6px; border-radius: 6px; border: 1px solid #c3e6cb;">${value ?? ""}</div>`;
            }
            return value ?? "";
        };
    }
}

/*This fn is used to catch the clicks so they dont open the row */
function setup_barcode_row_handlers(frm) {
    // Remove previous capture listener to prevent stacking on navigation
    if (frm._kl_barcode_capture_handler) {
        frm.wrapper.removeEventListener('click', frm._kl_barcode_capture_handler, true);
    }

    frm._kl_barcode_capture_handler = function (e) {
        // --- Generate Barcode button ---
        const btn = e.target.closest('.kl-barcode-btn');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            const gridRowEl = btn.closest('.grid-row');
            const cdn = gridRowEl && gridRowEl.dataset.name;
            if (cdn) {
                frappe.trigger_barcode_api(null, cdn, cur_frm.doc.name);
            }
            return;
        }

        // --- Open Barcodes link ---
        const link = e.target.closest('.kl-barcode-link');
        if (link) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            if (link.href) {
                window.open(link.href, '_blank');
            }
        }
    };

    // true = capture phase
    frm.wrapper.addEventListener('click', frm._kl_barcode_capture_handler, true);

    const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
    if (grid && grid.grid_rows) {
        grid.grid_rows.forEach(function (grid_row) {
            if (!grid_row.doc) return;
            grid_row.refresh_field('custom_generate_barcodes');
        });
    }
}

function set_warehouse_in_se(frm) {
    frm.set_query("t_warehouse", "items", function(doc, cdt, cdn) {
        console.log("t_warehouse query triggered! Parent custom_type:", doc.custom_type);
        if (doc.custom_type) {
            return {
                filters: {
                    "custom_type": doc.custom_type
                }
            };
        }
    });
}

