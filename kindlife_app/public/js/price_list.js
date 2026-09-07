frappe.ui.form.on('Price List', {
    refresh: function(frm) {
        console.log("hereee")
        
      
        setTimeout(() => {
            // Remove the default "Add / Edit Prices" button
            frm.remove_custom_button(__('Add / Edit Prices'));

            frm.add_custom_button(__('Item Price Management'), function() {
                show_price_management_dialog(frm);
            }, );
            
            // Add custom buttons with dropdown
            // frm.add_custom_button(__('Current Prices'), function() {
            //     frappe.set_route('query-report', 'Current Item Price', {
            //         'price_list': frm.doc.name
            //     });
            // }, __('Price Management'));
            
            // frm.add_custom_button(__('Pending Approvals'), function() {
            //     frappe.set_route('query-report', 'Pending Item Price Approval', {
            //         'price_list': frm.doc.name
            //     });
            // }, __('Price Management'));
            
        }, 100);
        }
    
});





function setup_price_management_buttons(frm) {
    // Remove existing price-related buttons
    frm.remove_custom_button(__('Add / Edit Prices'));
    
    // Create a comprehensive price management menu
    let price_menu = frm.add_custom_button(__('Price Management'), null, __('Actions'));
    
    // Add submenu items
    frm.add_custom_button(__('View Current Prices'), function() {
        frappe.set_route('query-report', 'Current Item Price Report', {
            'price_list': frm.doc.name
        });
    }, __('Price Management'));
    
    frm.add_custom_button(__('Add New Prices'), function() {
        frappe.route_options = {
            "price_list": frm.doc.name
        };
        frappe.new_doc("Item Price");
    }, __('Price Management'));
    
    frm.add_custom_button(__('Edit Existing Prices'), function() {
        frappe.route_options = {
            "price_list": frm.doc.name
        };
        frappe.set_route("List", "Item Price");
    }, __('Price Management'));
    
    frm.add_custom_button(__('Pending Approvals'), function() {
        frappe.set_route('query-report', 'Item Price Approval Pending Report', {
            'price_list': frm.doc.name
        });
    }, __('Price Management'));
    
    frm.add_custom_button(__('Price History'), function() {
        show_price_history_dialog(frm);
    }, __('Price Management'));
}

// Enhanced dialog for price management options
function show_price_management_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __('Price Management Options'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'price_options',
                options: `
                    <div class="price-management-options">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="card" style="margin-bottom: 15px; cursor: pointer;" onclick="viewCurrentPrices('${frm.doc.name}')">
                                    <div class="card-body text-center">
                                        <i class="fa fa-list-alt fa-2x text-primary"></i>
                                        <h5>Current Prices</h5>
                                        <p>View current active prices with approval status</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card" style="margin-bottom: 15px; cursor: pointer;" onclick="addEditPrices('${frm.doc.name}')">
                                    <div class="card-body text-center">
                                        <i class="fa fa-edit fa-2x text-success"></i>
                                        <h5>Add / Edit Prices</h5>
                                        <p>Manage item prices directly</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="card" style="margin-bottom: 15px; cursor: pointer;" onclick="viewPendingApprovals('${frm.doc.name}')">
                                    <div class="card-body text-center">
                                        <i class="fa fa-clock-o fa-2x text-warning"></i>
                                        <h5>Pending Approvals</h5>
                                        <p>Review price changes awaiting approval</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card" style="margin-bottom: 15px; cursor: pointer;" onclick="bulkPriceUpdate('${frm.doc.name}')">
                                    <div class="card-body text-center">
                                        <i class="fa fa-upload fa-2x text-info"></i>
                                        <h5>Bulk Import</h5>
                                        <p>Import prices from Excel/CSV</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <style>
                        .card { 
                            border: 1px solid #ddd; 
                            border-radius: 8px; 
                            transition: all 0.3s ease;
                        }
                        .card:hover { 
                            box-shadow: 0 4px 8px rgba(0,0,0,0.1); 
                            transform: translateY(-2px);
                        }
                        .card-body { 
                            padding: 20px; 
                        }
                        .card h5 { 
                            margin: 10px 0 5px 0; 
                            color: #333;
                        }
                        .card p { 
                            margin: 0; 
                            color: #666; 
                            font-size: 14px;
                        }
                    </style>
                `
            }
        ],
        primary_action_label: __('Close'),
        primary_action: function() {
            dialog.hide();
        }
    });
    
    dialog.show();
}

// Global functions for dialog actions
window.viewCurrentPrices = function(price_list) {
    frappe.set_route('query-report', 'Current Item Price', {
        'price_list': price_list
    });
    cur_dialog.hide();
};

window.addEditPrices = function(price_list) {
    frappe.route_options = {
        "price_list": price_list
    };
    frappe.set_route("List", "Item Price");
    cur_dialog.hide();
};

window.viewPendingApprovals = function(price_list) {
    frappe.set_route('query-report', 'Pending Item Price Approval', {
        'price_list': price_list
    });
    cur_dialog.hide();
};

window.bulkPriceUpdate = function(price_list) {
    // Method 1: Direct route to Data Import with Item Price pre-selected
    frappe.set_route('data-import', {
        'reference_doctype': 'Item Price'
    });
    
    // Alternative Method 2: Using frappe.route_options for better pre-filling
    // frappe.route_options = {
    //     'reference_doctype': 'Item Price'
    // };
    // frappe.set_route('data-import');
    
    // Method 3: Open Data Import in new tab (if preferred)
    // window.open(`${window.location.origin}/app/data-import/view/new?reference_doctype=Item%20Price`, '_blank');
    
    cur_dialog.hide();
};

function show_price_history_dialog(frm) {
    frappe.call({
        method: 'your_app.api.get_price_history',
        args: {
            'price_list': frm.doc.name
        },
        callback: function(r) {
            if (r.message) {
                // Show price history in a dialog
                // Implementation depends on your requirements
            }
        }
    });
}