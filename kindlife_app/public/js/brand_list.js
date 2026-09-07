// File: custom_app/public/js/brand_list.js
// Add this file to your custom app's public/js folder

frappe.listview_settings['Brand'] = {
    onload: function(listview) {
        // Add custom button to list view
        listview.page.add_action_item(__('Rename Selected'), function() {
            let selected_docs = listview.get_checked_items();
            
            if (selected_docs.length === 0) {
                frappe.msgprint(__('Please select at least one brand to rename.'));
                return;
            }
            
            // Show rename dialog
            show_rename_dialog(selected_docs, listview);
        });
    }
};

function show_rename_dialog(selected_docs, listview) {
    let dialog = new frappe.ui.Dialog({
        title: __('Rename Brands'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'selected_brands',
                options: `<div class="text-muted mb-3">
                    <strong>Selected Brands (${selected_docs.length}):</strong><br>
                    ${selected_docs.map(doc => `• ${doc.name}`).join('<br>')}
                </div>`
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldtype: 'Select',
                fieldname: 'rename_type',
                label: 'Rename Type',
                options: 'Individual\nBulk Pattern',
                default: 'Individual',
                onchange: function() {
                    toggle_rename_fields(dialog);
                }
            },
            {
                fieldtype: 'Column Break'
            },
            {
                fieldtype: 'Check',
                fieldname: 'merge_if_exists',
                label: 'Merge if target exists',
                default: 0,
                description: 'If checked, will merge with existing brand if new name already exists'
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'individual_fields',
                options: generate_individual_fields_html(selected_docs)
            },
            {
                fieldtype: 'Data',
                fieldname: 'bulk_prefix',
                label: 'Prefix',
                depends_on: 'eval:doc.rename_type=="Bulk Pattern"',
                description: 'Text to add before each brand name'
            },
            {
                fieldtype: 'Column Break',
                depends_on: 'eval:doc.rename_type=="Bulk Pattern"'
            },
            {
                fieldtype: 'Data',
                fieldname: 'bulk_suffix',
                label: 'Suffix',
                depends_on: 'eval:doc.rename_type=="Bulk Pattern"',
                description: 'Text to add after each brand name'
            }
        ],
        primary_action_label: __('Rename'),
        primary_action: function(values) {
            perform_rename(values, selected_docs, dialog, listview);
        },
        secondary_action_label: __('Cancel')
    });
    
    dialog.show();
}

function generate_individual_fields_html(selected_docs) {
    let html = '<div id="individual-rename-fields">';
    
    selected_docs.forEach((doc, index) => {
        html += `
            <div class="row mb-2">
                <div class="col-md-5">
                    <label class="text-muted">${doc.name}</label>
                </div>
                <div class="col-md-7">
                    <input type="text" 
                           class="form-control individual-rename-input" 
                           data-old-name="${doc.name}"
                           placeholder="Enter new name"
                           value="${doc.name}">
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    return html;
}

function toggle_rename_fields(dialog) {
    let rename_type = dialog.get_value('rename_type');
    let individual_div = dialog.$wrapper.find('#individual-rename-fields');
    
    if (rename_type === 'Individual') {
        individual_div.show();
    } else {
        individual_div.hide();
    }
}

function perform_rename(values, selected_docs, dialog, listview) {
    let rename_map = {};
    
    if (values.rename_type === 'Individual') {
        // Get individual rename values
        dialog.$wrapper.find('.individual-rename-input').each(function() {
            let old_name = $(this).data('old-name');
            let new_name = $(this).val().trim();
            
            if (new_name && new_name !== old_name) {
                rename_map[old_name] = new_name;
            }
        });
    } else {
        // Bulk pattern rename
        selected_docs.forEach(doc => {
            let new_name = (values.bulk_prefix || '') + doc.name + (values.bulk_suffix || '');
            if (new_name !== doc.name) {
                rename_map[doc.name] = new_name;
            }
        });
    }
    
    if (Object.keys(rename_map).length === 0) {
        frappe.msgprint(__('No changes detected. Please modify at least one brand name.'));
        return;
    }
    
    // Confirm rename operation
    frappe.confirm(
        __('Are you sure you want to rename {0} brand(s)?', [Object.keys(rename_map).length]),
        function() {
            // Close dialog and start rename process
            dialog.hide();
            
            // Show progress dialog
            // let progress_dialog = show_progress_dialog(Object.keys(rename_map).length);
            
            // Perform rename operations sequentially
            rename_brands_sequentially(rename_map, values.merge_if_exists, "", listview);
        }
    );
}

function show_progress_dialog(total_count) {
    let progress_dialog = new frappe.ui.Dialog({
        title: __('Renaming Brands'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'progress_html',
                options: `
                    <div class="progress mb-3">
                        <div class="progress-bar" role="progressbar" style="width: 0%"></div>
                    </div>
                    <div id="rename-status">Preparing to rename brands...</div>
                `
            }
        ]
    });
    
    progress_dialog.show();
    progress_dialog.no_cancel();
    return progress_dialog;
}

function rename_brands_sequentially(rename_map, merge_if_exists, progress_dialog, listview) {
    let brands = Object.keys(rename_map);
    let completed = 0;
    let errors = [];
    
    function rename_next_brand() {
        if (completed >= brands.length) {
            // All done
            // progress_dialog.hide();
            
            if (errors.length > 0) {
                frappe.msgprint({
                    title: __('Rename Complete with Errors'),
                    message: __('Successfully renamed {0} brands. {1} errors occurred:<br><br>{2}', 
                        [completed - errors.length, errors.length, errors.join('<br>')]),
                    indicator: 'orange'
                });
            } else {
                frappe.msgprint({
                    title: __('Rename Complete'),
                    message: __('Successfully renamed {0} brands.', [completed]),
                    indicator: 'green'
                });
            }
            
            // Refresh list view
            listview.refresh();
            return;
        }
        
        let old_name = brands[completed];
        let new_name = rename_map[old_name];
        
        // Update progress
        // let progress_percent = ((completed + 1) / brands.length) * 100;
        // progress_dialog.$wrapper.find('.progress-bar').css('width', progress_percent + '%');
        // progress_dialog.$wrapper.find('#rename-status').html(
        //     __('Renaming "{0}" to "{1}" ({2}/{3})', [old_name, new_name, completed + 1, brands.length])
        // );
        
        // Call our custom whitelisted method
        frappe.call({
            method: 'kindlife_app.api.brand_utils.bulk_rename_brands',
            args: {
                rename_data: {[old_name]: new_name},
                merge_if_exists: merge_if_exists
            },
            callback: function(response) {
                completed++;
                
                if (response.message && response.message.errors && response.message.errors.length > 0) {
                    // Handle errors from our custom method
                    response.message.errors.forEach(error => {
                        errors.push(__('Error renaming "{0}": {1}', [error.old_name, error.error]));
                    });
                }
                
                // Continue with next brand
                setTimeout(rename_next_brand, 100); // Small delay to prevent overwhelming
            },
            error: function(error) {
                completed++;
                errors.push(__('Error renaming "{0}": {1}', [old_name, error.message || 'Unknown error']));
                
                // Continue with next brand even on error
                setTimeout(rename_next_brand, 100);
            }
        });
    }
    
    // Start the rename process
    rename_next_brand();
}