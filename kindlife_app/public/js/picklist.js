const SCANNER_ALERT_DURATION = 10;

frappe.ui.form.on('Pick List', {
    custom_manually_picking: function (frm) {
        // Update warehouse field read-only property
        frm.fields_dict.locations.grid.update_docfield_property(
            "warehouse",
            "read_only",
            !frm.doc.custom_manually_picking
        );

        // Clear auto-assigned serial numbers and related fields when switching to manual picking
        if (frm.doc.custom_manually_picking && frm.doc.locations && frm.is_new()) {
            let has_changes = false;
            frm.doc.locations.forEach((row) => {
                if (row.serial_no || row.batch_no || row.serial_and_batch_bundle) {
                    row.serial_no = "";
                    row.serial_and_batch_bundle = "";
                    row.picked_qty = 0;
                    has_changes = true;
                }
            });

            if (has_changes) {
                frappe.show_alert(
                    __("Cleared auto-assigned serial numbers and batch numbers for manual picking"),
                    3
                );
                frm.refresh_field("locations");
            }
        }
    },
    onload: function (frm) {
        // Clear serial numbers on load to allow batch-based scanning
        frm.trigger('custom_manually_picking');

        // Initialize the custom serial scanner after a delay to not block UI
        setTimeout(() => {
            if (!frm.serial_scanner) {
                frm.serial_scanner = new PickListSerialScanner({
                    frm: frm
                });
            }
        }, 100);
    },


    check_scanning_status(frm) {
        if (!frm.doc.locations || frm.doc.locations.length === 0) return;

        let all_scanned = frm.doc.locations.every(row => row.picked_qty == row.qty);

        if (all_scanned) {
            frm.dashboard.clear_headline();
            frm.dashboard.set_headline(
                __("<span style='color:green; font-weight:600;'>✔ Scanning Completed</span>")
            );
        } else {
            frm.dashboard.clear_headline();
        }
    },

    setup(frm) {
        frappe.meta.get_docfield("Pick List Item", "picked_qty", frm.doc.name).formatter =
            function (value, df, options, doc) {
                if (value == doc.qty) {
                    return `<div style="
                            background-color: #d4edda;   /* light green */
                            color: #155724;              /* dark green text */
                            font-weight: 600;
                            text-align: center;
                            width: 100%;
                            height: 100%;
                            padding: 3px 6px;
                            border-radius: 6px;
                            border: 1px solid #c3e6cb;   /* subtle border */
                        ">
                            ${value ?? ""}
                        </div>`;
                } else {
                    return value ?? "";
                }
            };
    },

    refresh(frm) {
        // This trigers the code that is secifically writen to be executed when the custome_manually_picking field is changed
        // This is needed as if manually picking is selected, the warehouse field should be editable, but currently it is readonly when form is first loaded.
        // This line makes the field editable
        frm.trigger("custom_manually_picking");
        set_custom_type_based_on_role(frm);

        // Add buttons IMMEDIATELY - before any other processing
        add_go_to_dropdown_pl(frm);
        if (frm.doc.docstatus === 1) {
            add_delivery_note_button(frm);
            add_download_shipment_button(frm);
        }

        // Apply filter to parent_warehouse field to show only main warehouses
        frm.set_query("parent_warehouse", function () {
            return {
                filters: {
                    "custom_main_warehouse": 1
                }
            };
        });

        setTimeout(() => {
            if (is_warehouse_only_user()) {
                frm.remove_custom_button('Get Items');
            }

            // Remove Delivery Note button from Create dropdown
            if (frm.doc.docstatus === 1) {
                frm.remove_custom_button('Create Delivery Note', 'Create');
            }
        }, 500);

        // Run scanning status check after buttons are shown
        frm.trigger("check_scanning_status");
    },

    custom_scan_serial_no: function (frm) {
        if (frm.doc.custom_scan_serial_no && frm.serial_scanner) {
            frm.serial_scanner.process_serial_scan(frm.doc.custom_scan_serial_no);
        }
    },

    before_save(frm) {
        if (frm.doc.docstatus === 1) return;
        validate_so_references(frm);
    },

    before_submit(frm) {
        warn_multiple_sales_orders(frm);
    }
});

function warn_multiple_sales_orders(frm) {
    // Guard: re-entry after user confirmed — allow submit through
    if (frm._multi_so_confirmed) {
        frm._multi_so_confirmed = false;
        return;
    }

    const locations = frm.doc.locations || [];

    // Group row indexes by sales_order
    const so_to_rows = {};
    locations.forEach(r => {
        if (!r.sales_order) return;
        if (!so_to_rows[r.sales_order]) so_to_rows[r.sales_order] = [];
        so_to_rows[r.sales_order].push(r.idx);
    });

    const unique_sos = Object.keys(so_to_rows);
    if (unique_sos.length <= 1) return;

    const list_html = unique_sos.map((so, i) => {
        const row_items = so_to_rows[so].map(idx => `<li>${idx}</li>`).join('');
        return `<li style="margin-top:8px;"><b>${i + 1}. ${so}</b><ul style="margin-top:4px;">${row_items}</ul></li>`;
    }).join('');

    frappe.validated = false;
    frappe.confirm(
        `<p>This Pick List is linked to <b>${unique_sos.length} Sales Orders</b>. Are you sure you want to submit?</p>
        <ul style="margin-top:10px;">${list_html}</ul>`,
        () => { frm._multi_so_confirmed = true; frm.submit(); },
        () => { frappe.validated = false; }
    );
}

// Fetches Sales Order docs (one per unique SO) and returns a map of so_name -> items array
async function fetch_so_items_map(so_names) {
    const so_map = {};
    await Promise.all([...new Set(so_names)].map(so_name =>
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Sales Order', name: so_name }
        }).then(r => {
            if (r.message) {
                so_map[so_name] = (r.message.items || []).concat(r.message.packed_items || []);
            }
        })
    ));
    return so_map;
}

// Returns list of {idx, item_code, sales_order} for rows where item was not found in the SO.
async function autofill_sales_order_item(rows) {
    const so_map = await fetch_so_items_map(rows.map(r => r.sales_order));
    const errors = [];
    await Promise.all(rows.map(row => {
        const so_data = so_map[row.sales_order] || [];
        const soi = so_data.find(i => i.item_code === row.item_code);
        if (soi) {
            if (soi.parent_detail_docname) {
                return Promise.all([
                    frappe.model.set_value(row.doctype, row.name, 'sales_order_item', soi.parent_detail_docname),
                    frappe.model.set_value(row.doctype, row.name, 'product_bundle_item', soi.name)
                ]);
            } else {
                return frappe.model.set_value(row.doctype, row.name, 'sales_order_item', soi.name);
            }
        } else {
            errors.push({ idx: row.idx, item_code: row.item_code, sales_order: row.sales_order });
        }
    }));
    return errors;
}

// Builds an HTML error list and shows a msgprint, then resets the validation guard
function abort_so_validation(frm, title, indicator, body_html) {
    frm._so_validation_running = false;
    frappe.msgprint({ title: __(title), indicator: indicator, message: body_html });
}

// Builds a list of <li> strings from an array of error objects using a template fn
function build_error_list(errors, template_fn) {
    return errors.map(template_fn).join('');
}

async function validate_so_references(frm) {
    const locations = frm.doc.locations || [];

    // Guard: if we re-entered after validation
    //  save, allow through
    if (frm._so_validation_running) {
        frm._so_validation_running = false;
        return;
    }

    // Block save immediately — we'll re-trigger after async work
    frappe.validated = false;
    frm._so_validation_running = true;

    const rows_missing_so = locations.filter(r => !r.sales_order);
    const rows_need_soi   = locations.filter(r => r.sales_order);

    // Step 1: Auto-fill sales_order_item for rows that have SO but no SOI
    if (rows_need_soi.length) {
        const errors = await autofill_sales_order_item(rows_need_soi);
        if (errors.length) {
            abort_so_validation(frm, 'Item Not Found in Sales Order', 'red',
                `<p>The Sales Order mentioned in the following rows does not contain the corresponding item.</p>
                <p>Please make sure the Sales Order is correct.<br>
                <i>If you changed the Item Code on an existing row, delete the row and re-add it.</i></p>
                <ul>${build_error_list(errors, e =>
                    `<li style="margin-top:6px;">Row #${e.idx} &mdash; <b>${e.item_code}</b> &nbsp;|&nbsp; SO: <b>${e.sales_order}</b></li>`
                )}</ul>`
            );
            return;
        }
    }

    // Step 2: Block save if any rows are still missing sales_order
    if (rows_missing_so.length) {
        abort_so_validation(frm, 'Missing Sales Order Reference', 'orange',
            `<p>The following items are missing a Sales Order reference. Please add one before saving.</p>`
            + `<ul>${build_error_list(rows_missing_so, r =>
                `<li style="margin-top:6px;">Row #${r.idx} &mdash; <b>${r.item_code}</b></li>`
            )}</ul>`
        );
        return;
    }

    // All validations passed — trigger save
    frm.save();
}

// Add standalone Delivery Note button
function add_delivery_note_button(frm) {
    // Check if Pick List is closed
    if (frm.doc.status === 'Cancelled') return;

    // Show "Create Delivery Note" button
    frm.add_custom_button(__('Create Delivery Note'), function () {
        frappe.model.open_mapped_doc({
            method: "erpnext.stock.doctype.pick_list.pick_list.create_delivery_note",
            frm: frm
        });
    });
}


frappe.ui.form.on("Pick List Item", {
    custom_scanned_qty(frm, cdt, cdn) {
        frm.fields_dict["locations"].grid.refresh();
        frm.trigger("check_scanning_status");
    }
});

class PickListSerialScanner {
    constructor(opts) {
        this.frm = opts.frm;
        this.scan_field_name = "custom_scan_serial_no";
        this.scanned_qty_field = "picked_qty";
        this.scanned_serial_field = "serial_no";

        // Cache for batch and serial validation
        this.batch_cache = new Map(); // batch_no -> {item_code, warehouse, expiry_date}
        this.barcode_to_serial_map = new Map(); // custom_barcode -> serial_no
        this.serial_to_batch_map = new Map(); // serial_no -> batch_info
        this.available_serials = new Map(); // item_code+warehouse+batch -> [serial_nos]

        // Sound options
        this.success_sound = "submit";
        this.fail_sound = "error";

        // Track which row is currently being scanned
        this.current_scanning_row = null;

        // Add custom CSS for formatting
        this.add_custom_css();

        // Initialize Row Locking Mixin
        Object.assign(this, RowLockingMixin);
        this.initRowLocking({
            frm: this.frm,
            child_table_field: 'locations'
        });

        // Initialize scanner on form load
        this.setup_scanner();
    }

    add_custom_css() {
        // Add custom CSS for better visual formatting
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
                    
                    /* Hover effects for scanned cells */
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
                    
                    /* Batch info styling */
                    .batch-info {
                        font-size: 0.85em;
                        color: #666;
                        font-style: italic;
                        margin-top: 2px;
                    }
                    
                    .batch-warning {
                        background-color: #fff3cd;
                        border: 1px solid #ffeaa7;
                        color: #856404;
                        padding: 8px;
                        border-radius: 4px;
                        margin: 5px 0;
                    }
                    
                    .batch-success {
                        background-color: #d4edda;
                        border: 1px solid #c3e6cb;
                        color: #155724;
                        padding: 8px;
                        border-radius: 4px;
                        margin: 5px 0;
                    }
                </style>
            `);
        }
    }

    setup_scanner() {
        // Load batch and serial data for validation
        this.load_batch_and_serial_data();
        this.frm.refresh_field('locations');
    }

    // ============================================
    // Row Locking Methods (NEW)
    // ============================================

    // New method to load batch and available serial data
    load_batch_and_serial_data() {
        try {
            this.show_alert(__("Loading batch and serial data for validation..."), "blue");

            // Clear existing cache
            this.batch_cache.clear();
            this.barcode_to_serial_map.clear();
            this.serial_to_batch_map.clear();
            this.available_serials.clear();

            // Load batch information from pick list items
            this.frm.doc.locations.forEach(row => {
                if (row.batch_no) {
                    const batch_key = `${row.item_code}|${row.warehouse}|${row.batch_no}`;
                    this.batch_cache.set(batch_key, {
                        item_code: row.item_code,
                        warehouse: row.warehouse,
                        batch_no: row.batch_no,
                        qty_required: row.qty,
                        row_idx: row.idx
                    });
                }
            });

            // Load available serials from the system for each batch
            this.load_available_serials_for_batches();

        } catch (error) {
            console.error("Error loading batch and serial data:", error);
            this.show_alert(__("Error loading batch data: {0}", [error.message]), "red", SCANNER_ALERT_DURATION);
        }
    }

    // Load available serials for each batch from the system
    load_available_serials_for_batches() {
        const batch_list = Array.from(this.batch_cache.keys());

        if (batch_list.length === 0) {
            this.show_alert(__("No batches found for validation"), "orange", SCANNER_ALERT_DURATION);
            return;
        }

        // Call server method to get available serials for batches
        frappe.call({
            method: 'kindlife_app.api.pick_list.get_available_serials_for_batches',
            args: {
                'batches': batch_list,
                'pick_list_items': this.frm.doc.locations
            },
            callback: (response) => {
                if (response.message) {
                    this.process_available_serials(response.message);
                    this.show_alert(__("Batch validation data loaded successfully"), "green");
                } else {
                    this.show_alert(__("No serial data found for batches"), "orange", SCANNER_ALERT_DURATION);
                }
            },
            error: (err) => {
                console.error("Error loading available serials:", err);
                this.show_alert(__("Error loading available serials"), "red", SCANNER_ALERT_DURATION);
            }
        });
    }

    // Process the available serials data from server
    process_available_serials(serials_data) {
        serials_data.forEach(data => {
            // Map custom_barcode to serial_no
            this.barcode_to_serial_map.set(data.serial_no, data.serial_no);

            // Map serial_no to its batch info
            this.serial_to_batch_map.set(data.serial_no, {
                batch_no: data.batch_no,
                item_code: data.item_code,
                warehouse: data.warehouse
            });

            // Group serials by item+warehouse+batch
            const key = `${data.item_code}|${data.warehouse}|${data.batch_no}`;
            if (!this.available_serials.has(key)) {
                this.available_serials.set(key, []);
            }
            this.available_serials.get(key).push(data.serial_no);
        });

        console.log("Available serials loaded:", this.available_serials.size, "batch groups");
    }

    // Find the pick list row that matches the batch, warehouse, and item_code
    // AND has remaining quantity to be picked
    find_best_row_for_scan(serial_info) {
        return this.frm.doc.locations.find(row => 
            row.batch_no === serial_info.batch_no && 
            row.item_code === serial_info.item_code && 
            row.warehouse === serial_info.warehouse &&
            (row.picked_qty || 0) < row.qty
        );
    }

    async process_serial_scan(scanned_value) {
        try {
            // Clear the scan field immediately
            this.frm.set_value(this.scan_field_name, "");

            if (!scanned_value) {
                return;
            }

            // Check if batch data is loaded
            if (this.batch_cache.size === 0) {
                this.show_alert(__("Batch data not loaded. Please wait..."), "orange", SCANNER_ALERT_DURATION);
                await this.load_batch_and_serial_data();
                return;
            }

            // Get the serial number from the scanned barcode
            const serial_no = this.barcode_to_serial_map.get(scanned_value);

            if (!serial_no) {
                this.show_alert(__("Invalid Barcode {0} ", [scanned_value]), "red", SCANNER_ALERT_DURATION);
                this.play_fail_sound();
                return;
            }

            // Get batch info for this serial
            const serial_info = this.serial_to_batch_map.get(serial_no);

            if (!serial_info) {
                this.show_alert(__("Serial number {0} information not found", [serial_no]), "red", SCANNER_ALERT_DURATION);
                this.play_fail_sound();
                return;
            }

            // Track which row we'll update
            const target_row = this.find_best_row_for_scan(serial_info);

            if (!target_row) {
                // If we didn't find an available row, check if any row exists at all for this batch/wh
                const any_matching_row = this.frm.doc.locations.find(row => 
                    row.batch_no === serial_info.batch_no && 
                    row.item_code === serial_info.item_code && 
                    row.warehouse === serial_info.warehouse
                );

                if (any_matching_row) {
                    this.show_alert(__("All rows for batch {0} in warehouse {1} are already fully picked", 
                        [serial_info.batch_no, serial_info.warehouse]), "orange", SCANNER_ALERT_DURATION);
                } else {
                    this.show_alert(__("No pick list row found for batch {0} in warehouse {1}", 
                        [serial_info.batch_no, serial_info.warehouse]), "red", SCANNER_ALERT_DURATION);
                }
                this.play_fail_sound();
                return;
            }

            // ROW LOCKING CHECK (NEW)
            // Check if row is locked by another user
            if (await this.is_row_locked_by_other(target_row.idx)) {
                const lock_info = this.locked_rows.get(target_row.idx);
                this.show_alert(__("Row #{0} is being scanned by {1}", [target_row.idx, lock_info.user_full_name]), "orange", SCANNER_ALERT_DURATION);
                this.play_fail_sound();
                return;
            }

            // Try to acquire lock if not already held
            const lock_data = this.locked_rows.get(target_row.idx);
            const is_my_lock = lock_data && lock_data.user === frappe.session.user;
            
            if (!is_my_lock) {
                const lock_acquired = await this.try_lock_row(target_row.idx, target_row.item_code);
                if (!lock_acquired) {
                    this.play_fail_sound();
                    return;
                }
            }

            // Check if already scanned
            if (this.is_already_scanned(target_row, serial_no)) {
                this.show_alert(__("Serial No {0} already scanned", [serial_no]), "orange", SCANNER_ALERT_DURATION);
                this.play_fail_sound();
                return;
            }

            // Add to scanned serials and update quantity
            await this.add_scanned_serial(target_row, serial_no);

            this.show_alert(__("✅ Row #{0}: Serial {1} from batch {2} scanned successfully",
                [target_row.idx, serial_no, serial_info.batch_no]), "green");
            this.play_success_sound();

        } catch (error) {
            console.error("Error processing serial scan:", error);
            this.show_alert(__("Error processing scan: {0}", [error.message]), "red", SCANNER_ALERT_DURATION);
            this.play_fail_sound();
        }
    }

    // Find the pick list row that matches both batch and item_code (to handle multiple items with same batch)
    find_row_by_batch_and_item(batch_no, item_code) {
        return this.frm.doc.locations.find(row =>
            row.batch_no === batch_no && row.item_code === item_code
        );
    }



    is_already_scanned(row, serial_no) {
        // Check the serial_no field
        const row_serials = row.serial_no || "";

        const row_list = row_serials.split('\n').filter(s => s.trim());

        return row_list.includes(serial_no);
    }

    async add_scanned_serial(row, serial_no) {
        // Get current scanned serials
        const current_scanned = row[this.scanned_serial_field] || "";
        const current_qty = row[this.scanned_qty_field] || 0;

        // Add new serial number to tracking field
        const new_scanned_serials = current_scanned ?
            current_scanned + '\n' + serial_no :
            serial_no;

        // Update the row
        await frappe.model.set_value(row.doctype, row.name, this.scanned_serial_field, new_scanned_serials);
        await frappe.model.set_value(row.doctype, row.name, this.scanned_qty_field, current_qty + 1);

        // Refresh the form to show updated values
        this.frm.refresh_field('locations');
    }

    // Enhanced validation for batch-based scanning
    async validate_all_scanned_serials() {
        const validation_results = [];

        for (let item of this.frm.doc.locations) {
            const scanned_serials = (item.serial_no || "").split('\n').filter(s => s.trim());
            const required_qty = item.qty;
            const batch_no = item.batch_no;

            const item_result = {
                item_code: item.item_code,
                idx: item.idx,
                batch_no: batch_no,
                required_qty: required_qty,
                scanned_qty: scanned_serials.length,
                valid_serials: [],
                invalid_serials: [],
                wrong_batch_serials: []
            };

            // Validate each scanned serial
            scanned_serials.forEach(serial => {
                const serial_info = this.serial_to_batch_map.get(serial);

                if (!serial_info) {
                    item_result.invalid_serials.push(serial);
                } else if (serial_info.batch_no !== batch_no || serial_info.item_code !== item.item_code) {
                    item_result.wrong_batch_serials.push({
                        serial: serial,
                        expected_batch: batch_no,
                        expected_item: item.item_code,
                        actual_batch: serial_info.batch_no,
                        actual_item: serial_info.item_code
                    });
                } else {
                    item_result.valid_serials.push(serial);
                }
            });

            validation_results.push(item_result);
        }

        this.display_batch_validation_results(validation_results);
    }

    display_batch_validation_results(results) {
        let html = '<div class="validation-results">';

        results.forEach(item => {
            html += `<div class="item-validation" style="margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">`;
            html += `<h5>Row #${item.idx}: ${item.item_code}</h5>`;
            html += `<p><strong>Batch:</strong> ${item.batch_no} | <strong>Required:</strong> ${item.required_qty} | <strong>Scanned:</strong> ${item.scanned_qty}</p>`;

            if (item.valid_serials.length > 0) {
                html += `<p><strong style="color: green;">✅ Valid Serials (${item.valid_serials.length}):</strong><br>`;
                html += `<small>${item.valid_serials.join(', ')}</small></p>`;
            }

            if (item.wrong_batch_serials.length > 0) {
                html += `<p><strong style="color: orange;">⚠️ Wrong Batch/Item Serials (${item.wrong_batch_serials.length}):</strong><br>`;
                item.wrong_batch_serials.forEach(wrong => {
                    html += `<small>${wrong.serial} (Expected: Item ${wrong.expected_item}, Batch ${wrong.expected_batch} | Got: Item ${wrong.actual_item}, Batch ${wrong.actual_batch})</small><br>`;
                });
                html += `</p>`;
            }

            if (item.invalid_serials.length > 0) {
                html += `<p><strong style="color: red;">❌ Invalid/Unknown Serials (${item.invalid_serials.length}):</strong><br>`;
                html += `<small>${item.invalid_serials.join(', ')}</small></p>`;
            }

            html += `</div>`;
        });

        html += '</div>';

        frappe.msgprint({
            title: __('Batch-Based Serial Validation Results'),
            message: html,
            wide: true
        });
    }

    clear_all_scanned_data() {
        frappe.confirm(
            __('Are you sure you want to clear all scanned serial data?'),
            () => {
                // Track which rows were cleared (by idx)
                const cleared_row_indices = [];
                
                this.frm.doc.locations.forEach(item => {
                    // Clear scanned data
                    frappe.model.set_value(item.doctype, item.name, this.scanned_serial_field, '');
                    frappe.model.set_value(item.doctype, item.name, this.scanned_qty_field, 0);
                    
                    // Track cleared row index
                    cleared_row_indices.push(item.idx);
                });
                
                // Store cleared row indices in document flags (no DB change needed)
                if (!this.frm.doc.__cleared_rows) {
                    this.frm.doc.__cleared_rows = [];
                }
                this.frm.doc.__cleared_rows = this.frm.doc.__cleared_rows.concat(cleared_row_indices);
                
                this.frm.refresh_field('locations');

                this.show_alert(__('All scanned data cleared'), 'blue');
                this.current_scanning_row = null;
            }

        );
    }

    show_scanning_progress() {
        let progress_html = '<div class="scanning-progress">';
        let total_required_qty = 0;
        let total_scanned_qty = 0;

        this.frm.doc.locations.forEach(item => {
            const required_qty = item.qty;
            const scanned_qty = item[this.scanned_qty_field] || 0;

            total_required_qty += required_qty;
            total_scanned_qty += scanned_qty;

            let percentage = required_qty > 0 ? (scanned_qty / required_qty * 100).toFixed(1) : 0;
            let color = percentage == 100 ? '#28a745' : percentage > 0 ? '#ffc107' : '#dc3545';
            let icon = percentage == 100 ? '✅' : percentage > 0 ? '⏳' : '❌';

            progress_html += `
                <div class="progress-item" style="margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                    <strong>${icon} Row #${item.idx}: ${item.item_code}</strong><br>
                    <div class="batch-info">Batch: ${item.batch_no}</div>
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
                <h4 style="margin-bottom: 10px;">📊 Batch-Based Scanning Progress: ${overall_percentage}%</h4>
                <div style="background: #e9ecef; border-radius: 15px; height: 30px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, ${overall_color}, ${overall_color}aa); width: ${overall_percentage}%; height: 100%; border-radius: 15px; transition: width 0.5s ease;"></div>
                </div>
                <div style="margin-top: 10px; display: flex; justify-content: space-between;">
                    <small><strong>${total_scanned_qty}/${total_required_qty}</strong> total serials scanned</small>
                    <small>${this.frm.doc.locations.length} items/batches total</small>
                </div>
            </div>
        ` + progress_html + '</div>';

        frappe.msgprint({
            title: __('📈 Batch-Based Scanning Progress Report'),
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

// Add Go To dropdown button for Pick List
function add_go_to_dropdown_pl(frm) {
    // Get the first Pick List item to find the Sales Order
    if (!frm.doc.locations || frm.doc.locations.length === 0) {
        return;
    }

    // Find the first item with a sales_order
    const first_item_with_so = frm.doc.locations.find(item => item.sales_order);

    if (!first_item_with_so || !first_item_with_so.sales_order) {
        return;
    }

    const sales_order = first_item_with_so.sales_order;

    // Add Go To dropdown button
    // frm.add_custom_button(__('Go To'), function() {
    //     // This is just a placeholder - the actual navigation happens in the dropdown items
    // }, null, 'btn-default');

    // Add Sales Order option to the Go To dropdown
    frm.add_custom_button(__('Sales Order'), function () {
        frappe.set_route('Form', 'Sales Order', sales_order);
    }, __('Go To'));

    // Style the Go To button to match other forms
    setTimeout(() => {
        $('button:contains("Go To"):not([data-label*="Sales Order"])').each(function () {
            if ($(this).text().trim() === 'Go To') {
                $(this).removeClass('btn-default').addClass('btn-secondary');

            }
        });
    }, 100);
}

function add_download_shipment_button(frm) {
    frm.add_custom_button(__('Download Shipment PDF'), function() {
        // 1. Identify the linked Sales Order and Item Code from the first row
        const first_item = (frm.doc.locations || [])[0];
        const shipment_id = first_item ? first_item.custom_shipment_id : null;
        const awb_number = first_item ? first_item.custom_awb_number : null;

        if (!shipment_id) {
            frappe.msgprint(__('Shipment ID not found on Pick List items.'));
            return;
        }

        frappe.show_alert({
            message: __('Shipment ID: {0}, AWB: {1}', [shipment_id, awb_number]),
            indicator: 'blue'
        });

        /*
        // 3. Call the future API
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