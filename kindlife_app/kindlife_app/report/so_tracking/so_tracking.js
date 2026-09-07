// Copyright (c) 2025, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["SO Tracking"] = {
	"filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
        },
        {
            "fieldname": "customer",
            "label": __("Customer"),
            "fieldtype": "Link",
            "options": "Customer"
        },
        {
            "fieldname": "sales_order",
            "label": __("Sales Order"),
            "fieldtype": "Link",
            "options": "Sales Order"
        },
        {
            "fieldname": "po_no",
            "label": __("Buyer's PO"),
            "fieldtype": "Data"
        },
        {
            "fieldname": "item_code",
            "label": __("Item"),
            "fieldtype": "Link",
            "options": "Item"
        },
        {
            "fieldname": "so_status",
            "label": __("Sales Order Status"),
            "fieldtype": "Select",
            "options": "\nDraft\nTo Deliver and Bill\nTo Bill\nTo Deliver\nCompleted\nClosed\nOn Hold"
        },
        {
            "fieldname": "si_status",
            "label": __("Sales Invoice Status"),
            "fieldtype": "Select",
            "options": "\nDraft\nReturn\nCredit Note Issued\nSubmitted\nPaid\nPartly Paid\nUnpaid\nUnpaid and Discounted\nPartly Paid and Discounted\nOverdue and Discounted\nOverdue\nInternal Transfer"
        }
	],




    "formatter": function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        // --- Formatter for Pick Lists ---
        if (column.fieldname === "pick_lists") {
            if (!data || !data.pl_ui_details || data.pl_ui_details.length === 0) {
                return value; // Fallback to export value
            }
            let final_html = [];
            data.pl_ui_details.forEach(details => {
                let parts = [details.link_html, details.date, details.warehouse, details.status_html];
                final_html.push(`<div>${parts.filter(Boolean).join(' | ')}</div>`);
            });
            return final_html.join('');
        }
        
        // --- Formatter for Delivery Notes ---
        if (column.fieldname === "delivery_notes") {
            if (!data || !data.dn_ui_details || data.dn_ui_details.length === 0) {
                return value;
            }
            let final_html = [];
            data.dn_ui_details.forEach(details => {
                let parts = [details.link_html, details.date, details.status_html];
                final_html.push(`<div>${parts.filter(Boolean).join(' | ')}</div>`);
            });
            return final_html.join('');
        }

        // --- Formatter for Sales Invoices ---
        if (column.fieldname === "sales_invoices") {
            if (!data || !data.si_ui_details || data.si_ui_details.length === 0) {
                return value;
            }
            let final_html = [];
            data.si_ui_details.forEach(details => {
                let parts = [details.link_html, details.date, details.status_html];
                final_html.push(`<div>${parts.filter(Boolean).join(' | ')}</div>`);
            });
            return final_html.join('');
        }

        // For all other columns, return the default formatted value
        return value;
    },
	
	after_datatable_render: function () {
		let reportHeaders = document.querySelectorAll('.dt-cell');
		$('.datatable .dt-row').css({'position': 'static','height': 'auto',});
		$('.dt-row-filter').css('height', 0)
		$('.dt-instance-1 .dt-cell').css('height', 'auto')
		// $('.dt-cell .dt-cell__content').css({'display': 'flex', 'align-items': 'baseline', 'justify-content': 'center', 'flex-direction': 'column' })
		$('.datatable .dt-scrollable').css({'maxHeight': 'initial','height': 'auto','overflow-y':'hidden','overflow-x':'scroll'})
		for (let i = 0; i < reportHeaders.length; i++) {
			let reportHeader = reportHeaders[i];
			reportHeader.style.height = 'auto';
		}
		// document.querySelector("[data-original-title='Refresh']").click();
	},

	get_datatable_options(options) {
		return Object.assign(options, {
			events: {
				onSortColumn() {
					$('.datatable .dt-row').css({'position': 'static','height': 'auto',});
					$('.dt-row-filter').css('height', 0)
					$('.dt-instance-1 .dt-cell').css('height', 'auto')
					// $('.dt-cell .dt-cell__content').css({'display': 'flex', 'align-items': 'baseline', 'justify-content': 'center', 'flex-direction': 'column' })
					$('.datatable .dt-scrollable').css({'maxHeight': 'initial','height': 'auto','overflow-y':'hidden','overflow-x':'scroll'})
				}
			},
		});
	},




};
