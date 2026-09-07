/**
 * Generic Row Locking Mixin
 * 
 * Provides row-level locking functionality for any doctype with child table rows.
 * Uses Redis-based locks via frappe.cache() with auto-expiry and heartbeat system.
 * 
 * Usage:
 *   Object.assign(this, RowLockingMixin);
 *   this.initRowLocking({
 *       frm: this.frm,
 *       child_table_field: 'items'  // or 'locations', etc.
 *   });
 * 
 * Author: Development Team
 * Created: 2026-05-11
 * Version: 1.0.0
 */

const RowLockingMixin = {
    /**
     * Initialize row locking for any doctype.
     * 
     * @param {Object} config - Configuration object
     * @param {Object} config.frm - Frappe form object
     * @param {string} config.child_table_field - Child table field name (e.g., 'items', 'locations')
     */
    initRowLocking(config) {
        this.frm = config.frm;
        this.child_table_field = config.child_table_field;
        
        // Row Locking state
        this.locked_rows = new Map();           // idx -> lock_data
        this.current_locked_row = null;         // Currently locked row idx
        this.heartbeat_interval = null;         // Heartbeat timer
        this.lock_refresh_interval = null;      // Lock check timer
        this.HEARTBEAT_FREQUENCY = 4 * 60 * 1000;    // 4 minutes
        this.LOCK_CHECK_FREQUENCY = 30 * 1000;       // 30 seconds
        
        // Add CSS if not already added
        this._add_lock_css();
        
        // Initialize
        this.load_row_locks();
        this.start_lock_check();
    },
    
    /**
     * Add CSS styles for locked rows.
     */
        /**
     * Add CSS styles for locked rows.
     */
    _add_lock_css() {
        if ($('#row-locking-css').length) return;
        
        $('head').append(`
            <style id="row-locking-css">
                /* Row Locking Styles */
                .grid-row.row-locked {
                    background-color: #fff3cd !important;
                    opacity: 0.75;
                    position: relative;
                }
                
                .grid-row.row-locked::before {
                    content: "🔒";
                    position: absolute;
                    left: 60px;
                    top: 50%;
                    transform: translateY(-50%);
                    font-size: 11px;
                    z-index: 10;
                    pointer-events: none;
                }
                
                .grid-row.row-locked-by-me {
                    background-color: #d1ecf1 !important;
                    border-left: 3px solid #0c5460;
                    position: relative;
                }
                
                .grid-row.row-locked-by-me::before {
                    content: "🔓";
                    position: absolute;
                    left: 60px;
                    top: 50%;
                    transform: translateY(-50%);
                    font-size: 11px;
                    z-index: 10;
                    pointer-events: none;
                }
                
                /* Push first data column to the right */
                .grid-row.row-locked .grid-static-col[data-fieldname]:first-of-type,
                .grid-row.row-locked-by-me .grid-static-col[data-fieldname]:first-of-type {
                    padding-left: 35px !important;
                }
            </style>
        `);
    },


    
    /**
     * Load all row locks from Redis for this document.
     */
    async load_row_locks() {
        if (!this.frm.doc.name || this.frm.is_new()) return;

        try {
            const response = await frappe.call({
                method: 'kindlife_app.api.row_locking.get_all_row_locks',
                args: {
                    doc_name: this.frm.doc.name
                }
            });

            if (response.message) {
                this.locked_rows.clear();
                
                // Convert to Map: idx -> lock_data
                Object.keys(response.message).forEach(idx => {
                    this.locked_rows.set(parseInt(idx), response.message[idx]);
                });

                // Update UI
                this.update_row_lock_ui();
                
                console.log(`[Row Locking] Loaded ${this.locked_rows.size} row locks`);
            }
        } catch (error) {
            console.error("[Row Locking] Failed to load row locks:", error);
        }
    },
    
    /**
     * Try to acquire lock on a row before scanning.
     * 
     * @param {number} row_idx - Row index
     * @param {string} item_code - Item code for display
     * @returns {Promise<boolean>} - True if lock acquired, false otherwise
     */
    async try_lock_row(row_idx, item_code) {
        if (!this.frm.doc.name || this.frm.is_new()) {
            frappe.show_alert({
                message: __("Please save the document first"),
                indicator: "orange"
            });
            return false;
        }

        try {
            const response = await frappe.call({
                method: 'kindlife_app.api.row_locking.acquire_row_lock',
                args: {
                    doc_name: this.frm.doc.name,
                    row_idx: row_idx,
                    item_code: item_code
                }
            });

            if (response.message && response.message.success) {
                // Update local cache
                if (!response.message.is_refresh) {
                    // New lock acquired
                    this.locked_rows.set(row_idx, {
                        user: frappe.session.user,
                        user_full_name: frappe.session.user_fullname || frappe.session.user,
                        locked_at: new Date().toISOString(),
                        row_item_code: item_code
                    });
                    
                    this.current_locked_row = row_idx;
                    
                    // Start heartbeat if not already running
                    if (!this.heartbeat_interval) {
                        this.start_heartbeat();
                    }
                }
                
                this.update_row_lock_ui();
                return true;
            } else {
                // Lock failed - show who has it
                const msg = response.message.message || "Row is locked by another user";
                const locked_by = response.message.locked_by || "Unknown";
                const locked_at = this._format_time(response.message.locked_at);
                
                frappe.show_alert({
                    message: __("{0}<br><small>Locked by: {1} at {2}</small>", [msg, locked_by, locked_at]),
                    indicator: "orange"
                }, 5);
                
                return false;
            }
        } catch (error) {
            console.error("[Row Locking] Failed to acquire lock:", error);
            frappe.show_alert({
                message: __("Lock acquisition failed: {0}", [error.message]),
                indicator: "red"
            });
            return false;
        }
    },
    
    /**
     * Release lock on a row.
     * 
     * @param {number} row_idx - Row index
     * @param {boolean} force - Force release (admin only)
     * @returns {Promise<boolean>} - True if released, false otherwise
     */
    async release_lock(row_idx, force = false) {
        if (!this.frm.doc.name || this.frm.is_new()) return false;

        try {
            const response = await frappe.call({
                method: 'kindlife_app.api.row_locking.release_row_lock',
                args: {
                    doc_name: this.frm.doc.name,
                    row_idx: row_idx,
                    force: force
                }
            });

            if (response.message && response.message.success) {
                // Update local cache
                this.locked_rows.delete(row_idx);
                
                if (this.current_locked_row === row_idx) {
                    this.current_locked_row = null;
                }
                
                // Stop heartbeat if no more locks
                if (this.locked_rows.size === 0) {
                    this.stop_heartbeat();
                }
                
                this.update_row_lock_ui();
                return true;
            }
            
            return false;
        } catch (error) {
            console.error("[Row Locking] Failed to release lock:", error);
            return false;
        }
    },
    
    /**
     * Start heartbeat to keep locks alive.
     * Sends heartbeat every 4 minutes (lock TTL is 15 min).
     */
    start_heartbeat() {
        // Clear existing interval
        this.stop_heartbeat();
        
        this.heartbeat_interval = setInterval(async () => {
            if (this.current_locked_row !== null) {
                try {
                    await frappe.call({
                        method: 'kindlife_app.api.row_locking.refresh_lock_heartbeat',
                        args: {
                            doc_name: this.frm.doc.name,
                            row_idx: this.current_locked_row
                        }
                    });
                    
                    console.log(`[Row Locking] Heartbeat sent for row ${this.current_locked_row}`);
                } catch (error) {
                    console.error("[Row Locking] Heartbeat failed:", error);
                    // Lock may have expired, reload locks
                    await this.load_row_locks();
                }
            }
        }, this.HEARTBEAT_FREQUENCY);
        
        console.log("[Row Locking] Heartbeat started");
    },
    
    /**
     * Stop heartbeat timer.
     */
    stop_heartbeat() {
        if (this.heartbeat_interval) {
            clearInterval(this.heartbeat_interval);
            this.heartbeat_interval = null;
            console.log("[Row Locking] Heartbeat stopped");
        }
    },
    
    /**
     * Start periodic lock checking.
     * Checks for lock changes every 30 seconds.
     */
    start_lock_check() {
        // Clear existing interval
        this.stop_lock_check();
        
        this.lock_refresh_interval = setInterval(async () => {
            await this.load_row_locks();
        }, this.LOCK_CHECK_FREQUENCY);
        
        console.log("[Row Locking] Lock checking started");
    },
    
    /**
     * Stop lock checking timer.
     */
    stop_lock_check() {
        if (this.lock_refresh_interval) {
            clearInterval(this.lock_refresh_interval);
            this.lock_refresh_interval = null;
            console.log("[Row Locking] Lock checking stopped");
        }
    },
    
    /**
     * Update visual indicators for locked rows.
     */
    update_row_lock_ui() {
        if (!this.frm.fields_dict[this.child_table_field] || 
            !this.frm.fields_dict[this.child_table_field].grid) return;

        const grid = this.frm.fields_dict[this.child_table_field].grid;
        
        if (!grid.grid_rows) return;

        grid.grid_rows.forEach(grid_row => {
            if (!grid_row.doc) return;

            const row_idx = grid_row.doc.idx;
            const $row = grid_row.wrapper;
            
            // Remove all lock classes first
            $row.removeClass('row-locked row-locked-by-me');
            
            // Check if row is locked
            const lock_data = this.locked_rows.get(row_idx);
            
            if (lock_data) {
                const is_my_lock = lock_data.user === frappe.session.user;
                
                if (is_my_lock) {
                    $row.addClass('row-locked-by-me');
                    
                    // Add tooltip
                    $row.attr('title', __('Locked by you at {0}', [this._format_time(lock_data.locked_at)]));
                } else {
                    $row.addClass('row-locked');
                    
                    // Add tooltip
                    $row.attr('title', __('Locked by {0} at {1}', [
                        lock_data.user_full_name,
                        this._format_time(lock_data.locked_at)
                    ]));
                }
            } else {
                $row.removeAttr('title');
            }
        });
    },
    
    /**
     * Format ISO datetime string to readable format.
     * 
     * @param {string} iso_string - ISO datetime string
     * @returns {string} - Formatted time
     */
    _format_time(iso_string) {
        if (!iso_string) return '';
        
        try {
            const date = new Date(iso_string);
            return frappe.datetime.str_to_user(date.toISOString());
        } catch (error) {
            return iso_string;
        }
    },
    
    /**
     * Check if a row is locked by another user.
     * 
     * @param {number} row_idx - Row index
     * @returns {boolean} - True if locked by another user
     */
    is_row_locked_by_other(row_idx) {
        const lock_data = this.locked_rows.get(row_idx);
        
        if (!lock_data) return false;
        
        return lock_data.user !== frappe.session.user;
    },
    
    /**
     * Release all locks held by current user.
     */
    async release_all_my_locks() {
        if (!this.frm.doc.name || this.frm.is_new()) {
            frappe.msgprint(__('Please save the document first'));
            return;
        }

        // Confirm action
        frappe.confirm(
            __('Are you sure you want to release all your locks on this document?'),
            async () => {
                try {
                    const response = await frappe.call({
                        method: 'kindlife_app.api.row_locking.cleanup_my_locks'
                    });

                    if (response.message && response.message.success) {
                        frappe.show_alert({
                            message: __('Released {0} lock(s)', [response.message.count]),
                            indicator: 'green'
                        });

                        // Clear local cache
                        this.locked_rows.clear();
                        this.current_locked_row = null;
                        this.stop_heartbeat();

                        // Reload locks and update UI
                        await this.load_row_locks();
                    }
                } catch (error) {
                    console.error("[Row Locking] Failed to release locks:", error);
                    frappe.show_alert({
                        message: __("Failed to release locks: {0}", [error.message]),
                        indicator: "red"
                    });
                }
            }
        );
    },
    
    /**
     * Show dialog with all currently locked rows.
     */
    async show_locked_rows() {
        if (!this.frm.doc.name || this.frm.is_new()) {
            frappe.msgprint(__('Please save the document first'));
            return;
        }

        // Reload locks first
        await this.load_row_locks();

        if (this.locked_rows.size === 0) {
            frappe.msgprint({
                title: __('No Locked Rows'),
                message: __('There are currently no locked rows in this document.'),
                indicator: 'blue'
            });
            return;
        }

        // Build HTML table
        let html = `
            <div style="max-height: 400px; overflow-y: auto;">
                <table class="table table-bordered table-condensed" style="margin-bottom: 0;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="width: 60px;">${__('Row')}</th>
                            <th>${__('Item Code')}</th>
                            <th>${__('Locked By')}</th>
                            <th>${__('Locked At')}</th>
                            <th style="width: 100px;">${__('TTL')}</th>
                            <th style="width: 80px;">${__('Action')}</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        this.locked_rows.forEach((lock_data, row_idx) => {
            const is_my_lock = lock_data.user === frappe.session.user;
            const row_class = is_my_lock ? 'table-info' : 'table-warning';
            const icon = is_my_lock ? '🔓' : '🔒';
            const ttl_minutes = Math.floor((lock_data.ttl_remaining || 0) / 60);
            const item_code = lock_data.row_item_code || 'N/A';

            html += `
                <tr class="${row_class}">
                    <td class="text-center"><strong>${icon} ${row_idx}</strong></td>
                    <td>${item_code}</td>
                    <td>${lock_data.user_full_name}</td>
                    <td><small>${this._format_time(lock_data.locked_at)}</small></td>
                    <td class="text-center">${ttl_minutes} min</td>
                    <td class="text-center">
                        ${is_my_lock ? 
                            `<button class="btn btn-xs btn-danger release-lock-btn" data-row-idx="${row_idx}">
                                ${__('Release')}
                            </button>` : 
                            '<span class="text-muted">—</span>'
                        }
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        const d = new frappe.ui.Dialog({
            title: __('🔒 Locked Rows ({0})', [this.locked_rows.size]),
            fields: [
                {
                    fieldname: 'locks_html',
                    fieldtype: 'HTML',
                    options: html
                }
            ],
            primary_action_label: __('Refresh'),
            primary_action: async () => {
                await this.show_locked_rows();
            }
        });

        d.show();

        // Handle release button clicks
        d.$wrapper.find('.release-lock-btn').on('click', async (e) => {
            const row_idx = parseInt($(e.target).data('row-idx'));
            
            const released = await this.release_lock(row_idx);
            
            if (released) {
                frappe.show_alert({
                    message: __('Lock released for Row #{0}', [row_idx]),
                    indicator: 'green'
                });
                // Refresh the dialog
                d.hide();
                await this.show_locked_rows();
            }
        });
    },
    
    /**
     * Add row locking buttons to form.
     * Call this in the form's refresh event.
     */
    add_row_locking_buttons() {
        // Show Locked Rows
        this.frm.add_custom_button(__('Show Locked Rows'), async () => {
            await this.show_locked_rows();
        }, __('Row Locking'));

        // Release All My Locks
        this.frm.add_custom_button(__('Release All My Locks'), async () => {
            await this.release_all_my_locks();
        }, __('Row Locking'));
    }
};
