/**
 * Common utility functions for Kindlife App
 */

/**
 * Check if user has only warehouse-related roles (restricted user)
 * 
 * This function determines if a user should have restricted access to finance-related
 * features. Users with only the "Warehouse User" role (and no administrative roles)
 * are considered restricted users.
 * 
 * @returns {boolean} true if user has only warehouse roles, false if user has admin roles
 * 
 * @example
 * // Hide finance buttons for warehouse-only users
 * if (is_warehouse_only_user()) {
 *     frm.remove_custom_button('Purchase Invoice', 'Create');
 * }
 */
function is_warehouse_only_user() {
    // Get all user roles
    let user_roles = frappe.user_roles;
    
    // Define roles that are considered administrative/non-restricted
    const additional_roles = [
        'Accounts Manager',
        'Purchase Manager',
        'Sales Manager',
        'Stock Manager'
    ];
    
    // Check if user has any administrative role
    for (let role of user_roles) {
        if (is_admin_user(frappe.session.user, ...additional_roles)) {
            return false; // User has admin role, not restricted
        }
    }
    
    // If user has Warehouse User role and no admin roles, they are restricted
    return frappe.user.has_role('Warehouse User');
}


// Hide row edit icons in Purchase Order Item table for warehouse-only users
function hide_item_row_edit_icons(frm) {
    // Don't apply restrictions to Pick List - warehouse users need to edit Pick List items
    if (frm.doc.doctype === 'Pick List') {
        return;
    }
    
    // Hide edit icons in the items child table
    if (frm.fields_dict.items && frm.fields_dict.items.grid) {
        // Override each grid row's toggle_view method
        frm.fields_dict.items.grid.grid_rows.forEach(function(grid_row) {
            if (grid_row && grid_row.toggle_view) {
                // Store original toggle_view method
                if (!grid_row.original_toggle_view) {
                    grid_row.original_toggle_view = grid_row.toggle_view;
                }
                
                // Override toggle_view to do nothing for warehouse users
                grid_row.toggle_view = function() {
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
            
            frm.fields_dict.items.grid.setup_allow_bulk_edit = function() {
                if (!is_warehouse_only_user()) {
                    return this.original_setup_allow_bulk_edit.apply(this, arguments);
                }
                // For warehouse users, don't setup bulk edit (prevents row interactions)
            };
        }
        
        // Disable pointer events on grid rows for warehouse users but allow link fields
        if (is_warehouse_only_user()) {
            frm.fields_dict.items.grid.wrapper.find('.grid-row').css({
                'pointer-events': 'none',
                'cursor': 'default'
            });
            
            // Re-enable pointer events for link fields
            frm.fields_dict.items.grid.wrapper.find('.grid-row a[href]').css({
                'pointer-events': 'auto',
                'cursor': 'pointer'
            });
        }
        
        // Add CSS to hide edit icons and disable interactions for warehouse users
        if (!$('#warehouse-user-hide-edit-icons').length) {
            let warehouseUserCSS = '';
            if (is_warehouse_only_user()) {
                warehouseUserCSS = `
                    [data-doctype="Purchase Order"] .frappe-control[data-fieldname="items"] .grid-row,
                    [data-doctype="Sales Order"] .frappe-control[data-fieldname="items"] .grid-row,
                    [data-doctype="Purchase Receipt"] .frappe-control[data-fieldname="items"] .grid-row {
                        pointer-events: none !important;
                        cursor: default !important;
                    }
                    [data-doctype="Purchase Order"] .frappe-control[data-fieldname="items"] .grid-row:hover,
                    [data-doctype="Sales Order"] .frappe-control[data-fieldname="items"] .grid-row:hover,
                    [data-doctype="Purchase Receipt"] .frappe-control[data-fieldname="items"] .grid-row:hover {
                        background-color: inherit !important;
                    }
                    [data-doctype="Purchase Order"] .frappe-control[data-fieldname="items"] .grid-row a[href],
                    [data-doctype="Sales Order"] .frappe-control[data-fieldname="items"] .grid-row a[href],
                    [data-doctype="Purchase Receipt"] .frappe-control[data-fieldname="items"] .grid-row a[href] {
                        pointer-events: auto !important;
                        cursor: pointer !important;
                    }
                `;
            }
            
            $('<style id="warehouse-user-hide-edit-icons">')
                .text(`
                    [data-doctype="Purchase Order"] .grid-row .btn-open-row,
                    [data-doctype="Purchase Order"] .grid-row .grid-row-open,
                    [data-doctype="Purchase Order"] .grid-row .grid-row-check:hover + .grid-row-open,
                    [data-doctype="Sales Order"] .grid-row .btn-open-row,
                    [data-doctype="Sales Order"] .grid-row .grid-row-open,
                    [data-doctype="Sales Order"] .grid-row .grid-row-check:hover + .grid-row-open,
                    [data-doctype="Purchase Receipt"] .grid-row .btn-open-row,
                    [data-doctype="Purchase Receipt"] .grid-row .grid-row-open,
                    [data-doctype="Purchase Receipt"] .grid-row .grid-row-check:hover + .grid-row-open {
                        display: none !important;
                    }
                    ${warehouseUserCSS}
                `)
                .appendTo('head');
        }
        
        // Override the grid's make_row method to apply restrictions to new rows
        if (!frm.fields_dict.items.grid.original_make_row) {
            frm.fields_dict.items.grid.original_make_row = frm.fields_dict.items.grid.make_row;
            
            frm.fields_dict.items.grid.make_row = function(doc, idx, columns) {
                // Call original make_row
                var row = this.original_make_row.apply(this, arguments);
                
                // Apply restrictions to the new row if warehouse user
                if (is_warehouse_only_user() && row && row.toggle_view) {
                    if (!row.original_toggle_view) {
                        row.original_toggle_view = row.toggle_view;
                    }
                    
                    row.toggle_view = function() {
                        return false; // Prevent row expansion
                    };
                }
                
                return row;
            };
        }
    }
}

// Making this fn as this is used in many places
let ADMIN_ROLES = [
    'Administrator',
    'System Manager',
]


// This fn tells if a given user has an admin role or not
// In come cases, we might need tocheck for orher roles as well, then users can give list of more roles as well
function is_admin_user(user, ...extra_roles){
    if (!user){
        user = frappe.session.user
    }
    //  Get all roles of user
    const user_roles = frappe.user_roles
    const roles_to_check = [...ADMIN_ROLES, ...extra_roles];

    //  Tell if the user has any admin roles
    return user_roles.some(role => roles_to_check.includes(role));

}


/**
 * Set the custom_type field value and read-only state based on the current user's role.
 * - Admins and users with both B2B+B2C roles can freely edit the field.
 * - Single-role users have the field auto-set to their role and made read-only.
 *
 * @param {object} frm - The Frappe form object
 */
function set_custom_type_based_on_role(frm) {
    const has_b2b = frappe.user.has_role("B2B");
    const has_b2c = frappe.user.has_role("B2C");
    const is_admin = is_admin_user(frappe.session.user);

    // If user has both permissions or is admin, allow them to select the type
    if ((has_b2b && has_b2c) || is_admin) {
        frm.set_df_property('custom_type', 'read_only', 0);
    }

    // Set the custom_type based on roles
    else {
        if (has_b2b) { frm.set_value('custom_type', 'B2B'); }
        else if (has_b2c) { frm.set_value('custom_type', 'B2C'); }
        else { frm.set_value('custom_type', 'B2B'); }

        // In any case, if user is not admin, or does not have both permissions, make the field read-only
        frm.set_df_property('custom_type', 'read_only', 1);
    }
}