frappe.query_reports["Pending Item Price Approval"] = {
    "filters": [
        {
            "fieldname": "price_list",
            "label": __("Price List"),
            "fieldtype": "Link",
            "options": "Price List"
        },
        {
            "fieldname": "item_code",
            "label": __("Item"),
            "fieldtype": "Link",
            "options": "Item"
        }
    ],
    
    "onload": function(report) {
        // Add bulk action buttons
        report.page.add_inner_button(__('Bulk Approve Selected'), function() {
            bulk_action('approve',report);
        }, __('Actions'));
        
        report.page.add_inner_button(__('Bulk Reject Selected'), function() {
            bulk_action('reject',report);
        }, __('Actions'));
        
        // report.page.add_inner_button(__('Select All'), function() {
        //     toggle_all_checkboxes(true);
        // }, __('Selection'));
        
        // report.page.add_inner_button(__('Deselect All'), function() {
        //     toggle_all_checkboxes(false);
        // }, __('Selection'));
        
        // Add custom CSS for better checkbox styling
        $('<style>')
            .text(`
                .row-check {
                    transform: scale(1.2);
                    margin: 0;
                }
                .bulk-actions-section {
                    padding: 10px;
                    background: #f8f9fa;
                    border-bottom: 1px solid #dee2e6;
                    margin-bottom: 10px;
                }
                .selected-count {
                    font-weight: bold;
                    color: #007bff;
                }
            `)
            .appendTo('head');
    },
	get_datatable_options(options) {
        return Object.assign(options, {
            checkboxColumn: true,
        });
    },
    
    "formatter": function(value, row, column, data, default_formatter) {
        if (column.fieldname == "actions") {
            return `
                <div style="display: flex; gap: 3px; justify-content: center;">
                    <button class='btn btn-xs btn-success' 
                            style='padding: 2px 6px; font-size: 10px;'
                            onclick='approvePrice("${data.name}")'
                            title='Approve'>
                        <i class="fa fa-check"></i>
                    </button>
                    <button class='btn btn-xs btn-danger' 
                            style='padding: 2px 6px; font-size: 10px;'
                            onclick='rejectPrice("${data.name}")'
                            title='Reject'>
                        <i class="fa fa-times"></i>
                    </button>
                </div>
            `;
        }
        
        return default_formatter(value, row, column, data);
    }
};

// Global functions for individual actions
window.approvePrice = function(item_price_name) {
    frappe.confirm(
        __('Are you sure you want to approve this price change?'),
        function() {
            frappe.call({
                method: 'kindlife_app.api.item_price.bulk_approve_prices',
                args: {
                    'item_price_names': [item_price_name]
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Price approved successfully'),
                            indicator: 'green'
                        });
                        frappe.query_report.refresh();
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            message: r.message ? r.message.message : __('Failed to approve price'),
                            indicator: 'red'
                        });
                    }
                }
            });
        }
    );
};

window.rejectPrice = function(item_price_name) {
    frappe.confirm(
        __('Are you sure you want to reject this price change?'),
        function() {
            frappe.call({
                method: 'kindlife_app.api.item_price.bulk_reject_prices',
                args: {
                    'item_price_names': [item_price_name]
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Price rejected successfully'),
                            indicator: 'orange'
                        });
                        frappe.query_report.refresh();
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            message: r.message ? r.message.message : __('Failed to reject price'),
                            indicator: 'red'
                        });
                    }
                }
            });
        }
    );
};

// Bulk action functions
function bulk_action(action, report) {
    let selected_items = get_selected_items(report);
    
    if (selected_items.length === 0) {
        frappe.msgprint(__('Please select at least one item'));
        return;
    }
    
    let action_text = action === 'approve' ? 'approve' : 'reject';
    let method = action === 'approve' ? 'bulk_approve_prices' : 'bulk_reject_prices';
    
    frappe.confirm(
        __(`Are you sure you want to ${action_text} ${selected_items.length} selected item(s)?`),
        function() {
            frappe.call({
                method: `kindlife_app.api.item_price.${method}`,
                args: {
                    'item_price_names': selected_items
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        let count = action === 'approve' ? r.message.approved_count : r.message.rejected_count;
                        frappe.show_alert({
                            message: __(`Successfully ${action_text}ed ${count} item(s)`),
                            indicator: action === 'approve' ? 'green' : 'orange'
                        });
                        
                        if (r.message.failed_items && r.message.failed_items.length > 0) {
                            frappe.msgprint({
                                title: __('Partial Success'),
                                message: __('Some items failed to process:') + '<br>' + 
                                        r.message.failed_items.join('<br>'),
                                indicator: 'yellow'
                            });
                        }
                        
                        report.refresh();
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            message: r.message ? r.message.message : __(`Failed to ${action_text} selected items`),
                            indicator: 'red'
                        });
                    }
                }
            });
        }
    );
}

function get_selected_items(report) {
    let selected_items = [];
    
    if (report && report.datatable) {
        // Get selected row indices
        let selected_indexes = report.datatable.rowmanager.getCheckedRows();
        
        // Get the actual data for selected rows
        selected_indexes.forEach(function(index) {
            if (report.data && report.data[index]) {
                selected_items.push(report.data[index].name);
            }
        });
    }
    
    return selected_items;
}

function toggle_all_checkboxes(select) {
    $('.row-check').prop('checked', select);
    updateSelectionCount();
}

function updateSelectionCount() {
    let selected_count = $('.row-check:checked').length;
    let total_count = $('.row-check').length;
    
    // Update selection info in the report header
    let selection_info = $(`.selection-info`);
    if (selection_info.length === 0) {
        $('.report-wrapper .page-head').after(`
            <div class="bulk-actions-section">
                <span class="selection-info">
                    Selected: <span class="selected-count">0</span> of <span class="total-count">${total_count}</span>
                </span>
            </div>
        `);
        selection_info = $('.selection-info');
    }
    
    selection_info.find('.selected-count').text(selected_count);
    selection_info.find('.total-count').text(total_count);
    
    // Show/hide bulk action buttons based on selection
    if (selected_count > 0) {
        $('.bulk-actions-section').addClass('has-selection');
    } else {
        $('.bulk-actions-section').removeClass('has-selection');
    }
}