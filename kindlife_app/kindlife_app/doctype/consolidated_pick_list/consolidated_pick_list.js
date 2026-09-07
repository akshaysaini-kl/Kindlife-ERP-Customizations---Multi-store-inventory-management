// Copyright (c) 2025, Auriga IT and contributors
// For license information, please see license.txt

frappe.ui.form.on("Consolidated Pick List", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Get Items'), () => {
				show_pick_list_selector(frm);
			});
		}

		// Apply filter to warehouse field to show only main warehouses
		frm.set_query("warehouse", function () {
			return {
				filters: {
					"custom_main_warehouse": 1
				}
			};
		});

		// Load pick list details for the collapsible HTML table
		if (!frm.is_new() && frm.doc.items && frm.doc.items.length > 0) {
			load_pick_list_details(frm);
		}
	}
});

// Phase 4 & 5: Load and display pick list details in collapsible HTML table
function load_pick_list_details(frm) {
	frappe.call({
		method: 'kindlife_app.kindlife_app.doctype.consolidated_pick_list.consolidated_pick_list.get_pick_list_details',
		args: { cpl_name: frm.doc.name },
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				let html = build_pick_list_details_table(r.message);
				frm.fields_dict.pick_list_details.$wrapper.html(html);

				// Attach collapsible handlers after rendering
				setTimeout(() => {
					setup_cpl_collapsible_handlers();
				}, 100);
			} else {
				frm.fields_dict.pick_list_details.$wrapper.html(
					'<span style="color: #888; font-style: italic;">No linked Pick Lists found.</span>'
				);
			}
		}
	});
}

// Build the collapsible HTML table for pick list details
function build_pick_list_details_table(pick_lists) {
	let html = `
		<div style="margin-bottom: 10px; padding: 12px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #2490ef;">
			<h5 style="margin-bottom: 15px; color: #2490ef; font-weight: 600;">📋 Linked Pick Lists (${pick_lists.length})</h5>
			<table class="table table-bordered" style="margin-bottom: 0; background: white;">
				<thead style="background: #f1f3f4;">
					<tr>
						<th style="width: 40px; text-align: center;"></th>
						<th>Pick List</th>
						<th style="width: 120px;">Status</th>
						<th style="width: 120px;">Scanning %</th>
						<th>Customer</th>
					</tr>
				</thead>
				<tbody>
	`;

	pick_lists.forEach((pl, idx) => {
		let row_id = `pl-${idx}`;

		// Status color
		let status_color = '#6c757d';
		if (pl.status === 'Completed' || pl.status === 'Closed') {
			status_color = '#28a745';
		} else if (pl.status === 'Open') {
			status_color = '#007bff';
		} else if (pl.status === 'Partly Delivered') {
			status_color = '#ff9800';
		}

		// Scanning progress bar color
		let scan_percent = pl.scanning_percent || 0;
		let scan_color = scan_percent >= 100 ? '#28a745' : scan_percent > 0 ? '#ffc107' : '#dc3545';
		let scan_label = scan_percent >= 100
			? '<span style="color: #28a745; font-weight: 600;">✔ Complete</span>'
			: `<span style="font-weight: 500;">${scan_percent.toFixed(1)}%</span>`;

		html += `
			<tr class="cpl-collapsible-row" data-target="${row_id}" style="cursor: pointer;">
				<td style="text-align: center;">
					<i class="fa fa-chevron-right cpl-expand-icon" style="color: #666;"></i>
				</td>
				<td>
					<a href="/app/pick-list/${pl.name}" target="_blank"
					   style="color: #2490ef; text-decoration: none; font-weight: 500;"
					   onclick="event.stopPropagation();">${pl.name}</a>
				</td>
				<td>
					<span style="color: ${status_color}; font-weight: 500;">${pl.status}</span>
				</td>
				<td>
					<div style="background: #e9ecef; border-radius: 8px; height: 18px; overflow: hidden; margin-bottom: 2px;">
						<div style="background: ${scan_color}; width: ${Math.min(scan_percent, 100)}%; height: 100%; border-radius: 8px; transition: width 0.3s ease;"></div>
					</div>
					${scan_label}
				</td>
				<td>${pl.customer_name || pl.customer || '-'}</td>
			</tr>
			<tr id="${row_id}" class="cpl-collapsible-content" style="display: none;">
				<td colspan="5" style="padding: 15px; background: #f9f9f9;">
					${build_pl_items_detail_table(pl.items || [])}
				</td>
			</tr>
		`;
	});

	html += `
				</tbody>
			</table>
		</div>
	`;

	return html;
}

// Build the items detail table for each pick list (expanded view)
function build_pl_items_detail_table(items) {
	if (items.length === 0) {
		return '<em style="color: #888;">No items found</em>';
	}

	let html = `
		<table class="table table-sm" style="margin-bottom: 0;">
			<thead>
				<tr style="background: #e3f2fd;">
					<th>Item Code</th>
					<th>Item Name</th>
					<th>Batch</th>
					<th>Warehouse</th>
					<th style="text-align: right;">Qty</th>
					<th style="text-align: right;">Picked Qty</th>
					<th style="text-align: center;">Status</th>
				</tr>
			</thead>
			<tbody>
	`;

	items.forEach(item => {
		let picked = item.picked_qty || 0;
		let required = item.qty || 0;
		let is_complete = picked >= required && required > 0;
		let status_html = is_complete
			? '<span style="color: #28a745; font-weight: 600;">✔</span>'
			: `<span style="color: #dc3545;">${picked}/${required}</span>`;

		html += `
			<tr>
				<td><strong>${item.item_code}</strong></td>
				<td>${item.item_name || ''}</td>
				<td>${item.batch_no || '-'}</td>
				<td>${item.warehouse || '-'}</td>
				<td style="text-align: right;">${required}</td>
				<td style="text-align: right;">
					<span style="color: ${is_complete ? '#28a745' : '#dc3545'}; font-weight: 500;">${picked}</span>
				</td>
				<td style="text-align: center;">${status_html}</td>
			</tr>
		`;
	});

	html += '</tbody></table>';
	return html;
}

// Setup click handlers for collapsible functionality (scoped to CPL)
function setup_cpl_collapsible_handlers() {
	$('.cpl-collapsible-row').off('click').on('click', function (e) {
		// Don't toggle if clicking a link
		if ($(e.target).is('a') || $(e.target).closest('a').length) {
			return;
		}

		let target_id = $(this).data('target');
		let content_row = $('#' + target_id);
		let icon = $(this).find('.cpl-expand-icon');

		if (content_row.is(':visible')) {
			content_row.hide();
			icon.removeClass('fa-chevron-down').addClass('fa-chevron-right');
		} else {
			content_row.show();
			icon.removeClass('fa-chevron-right').addClass('fa-chevron-down');
		}
	});
}

function show_pick_list_selector(frm) {
	// Use MultiSelectDialog to make single API call with all selected pick lists
	let get_query_filters = {
		docstatus: 0,
		// status: ['in', ['Open', 'Partly Delivered']],
		custom_consolidate_pick_list: ['is', 'not set']
	};

	if (frm.doc.company) {
		get_query_filters.company = frm.doc.company;
	}

	// Filter by type (B2B/B2C) based on consolidated pick list type
	if (frm.doc.type) {
		get_query_filters.custom_type = frm.doc.type;
	}

	// Filter by warehouse if specified in consolidated pick list
	if (frm.doc.warehouse) {
		get_query_filters.parent_warehouse = frm.doc.warehouse;
	}

	const dialog = new frappe.ui.form.MultiSelectDialog({
		doctype: 'Pick List',
		target: frm,
		setters: [
			{
				fieldtype: 'Link',
				label: __('Company'),
				fieldname: 'company',
				options: 'Company',
				default: frm.doc.company
			},
			{
				fieldtype: 'Select',
				label: __('Type'),
				fieldname: 'custom_type',
				options: 'B2B\nB2C',
				default: frm.doc.type
			},
			{
				fieldtype: 'Link',
				label: __('Parent Warehouse'),
				fieldname: 'parent_warehouse',
				options: 'Warehouse',
				default: frm.doc.warehouse
			}
		],
		date_field: 'creation',
		columns: ['name', 'company', 'sales_order', 'status'],
		get_query() {
			return {
				query: 'kindlife_app.kindlife_app.doctype.consolidated_pick_list.consolidated_pick_list.get_pick_list_query',
				filters: get_query_filters
			};
		},
		primary_action_label: __('Get Items'),
		action(selections) {
			if (!selections || selections.length === 0) {
				frappe.msgprint(__('Please select at least one Pick List'));
				return;
			}

			// Make single API call with all selected pick lists
			frappe.call({
				method: 'kindlife_app.kindlife_app.doctype.consolidated_pick_list.consolidated_pick_list.get_items_from_pick_lists',
				args: {
					source_name: selections,
					target_doc: frm.doc
				},
				freeze: true,
				freeze_message: __('Consolidating items from {0} Pick Lists...', [selections.length]),
				callback: function (r) {
					if (r.message) {
						// Clear existing items
						frm.clear_table('items');

						// Add consolidated items
						if (r.message.items) {
							r.message.items.forEach(function (item) {
								let row = frm.add_child('items');
								row.item = item.item;
								row.qty = item.qty;
								row.warehouse = item.warehouse;
								row.batch = item.batch;
								row.pick_lists = item.pick_lists;
								row.scanned_serials = '';
							});
						}

						frm.refresh_field('items');
						frm.dirty();
						dialog.dialog.hide();

						frappe.show_alert({
							message: __('Successfully consolidated items from {0} Pick Lists', [selections.length]),
							indicator: 'green'
						});
					}
				},
				error: function (r) {
					frappe.msgprint(__('Error consolidating items. Please try again.'));
				}
			});
		}
	});
}

