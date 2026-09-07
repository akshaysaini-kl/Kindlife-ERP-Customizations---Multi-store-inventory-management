frappe.listview_settings['Pick List'] = {
    get_indicator: function (doc) {
        let percent = doc.custom_scanning_percent || 0;
        if (percent >= 100) {
            return [__('Scanning Complete'), 'green', 'custom_scanning_percent,>=,100'];
        } else if (percent > 0) {
            return [__('Scanning In Progress ({0}%)', [percent.toFixed(1)]), 'orange', 'custom_scanning_percent,>,0|custom_scanning_percent,<,100'];
        }
        // No indicator for 0% - keeps list clean
    },
    onload: function (listview) {
        // Add "Generate CPL" button as a page action
        listview.page.add_action_item(__('Generate CPL'), function () {
            let selected = listview.get_checked_items();
            if (!selected || selected.length === 0) {
                frappe.msgprint(__('Please select at least one Pick List'));
                return;
            }

            // Validate: all selected must be draft (scanning happens in draft mode)
            let invalid = selected.filter(d => d.docstatus !== 0);
            if (invalid.length > 0) {
                frappe.msgprint(__('Only draft Pick Lists can be consolidated. Remove submitted/cancelled selections.'));
                return;
            }

            let pick_list_names = selected.map(d => d.name);

            // Show dialog for Type and Warehouse selection
            let dialog = new frappe.ui.Dialog({
                title: __('Generate Consolidated Pick List'),
                fields: [
                    {
                        fieldname: 'type',
                        fieldtype: 'Select',
                        label: __('Type'),
                        options: 'B2B\nB2C',
                        default: 'B2C',
                        reqd: 1
                    },
                    {
                        fieldname: 'warehouse',
                        fieldtype: 'Link',
                        label: __('Warehouse'),
                        options: 'Warehouse',
                        get_query: function () {
                            return {
                                filters: { 'custom_main_warehouse': 1 }
                            };
                        }
                    },
                    {
                        fieldname: 'selected_info',
                        fieldtype: 'HTML',
                        options: `<div class="text-muted" style="margin-top: 5px;">
                            <strong>${pick_list_names.length}</strong> Pick List(s) selected:
                            <br><small>${pick_list_names.join(', ')}</small>
                        </div>`
                    }
                ],
                primary_action_label: __('Generate CPL'),
                primary_action: function (values) {
                    dialog.hide();
                    frappe.call({
                        method: 'kindlife_app.kindlife_app.doctype.consolidated_pick_list.consolidated_pick_list.create_cpl_from_pick_lists',
                        args: {
                            pick_list_names: pick_list_names,
                            type: values.type,
                            warehouse: values.warehouse || ''
                        },
                        freeze: true,
                        freeze_message: __('Generating Consolidated Pick List...'),
                        callback: function (r) {
                            if (r.message) {
                                frappe.show_alert({
                                    message: __('CPL {0} created successfully', [r.message]),
                                    indicator: 'green'
                                }, 5);
                                frappe.set_route('Form', 'Consolidated Pick List', r.message);
                            }
                        }
                    });
                }
            });

            dialog.show();
        });

        // Phase 3: Add "CPL Not Generated" quick filter button
        listview.page.add_inner_button(__('CPL Not Generated'), function () {
            listview.filter_area.clear();
            listview.filter_area.add([
                ['Pick List', 'custom_consolidate_pick_list', 'is', 'not set'],
                ['Pick List', 'docstatus', '=', 1]
            ]);
            listview.refresh();
        });
    }
};
