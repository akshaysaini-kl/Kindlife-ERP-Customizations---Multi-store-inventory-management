// Copyright (c) 2025, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["PO Tracking"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"fieldtype": "Date",
			"label": "From Date",
			"mandatory": 0,
			"wildcard_filter": 0,
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		   },
		   {
			"fieldname": "to_date",
			"fieldtype": "Date",
			"label": "To Date",
			"mandatory": 0,
			"wildcard_filter": 0,
			"default": frappe.datetime.get_today()
		   },
		   {
			"fieldname": "supplier",
			"fieldtype": "Link",
			"label": "Supplier",
			"mandatory": 0,
			"options": "Supplier",
			"wildcard_filter": 0
		   },
		   {
			"fieldname": "purchase_order",
			"fieldtype": "Link",
			"label": "Purchase Order",
			"mandatory": 0,
			"options": "Purchase Order",
			"wildcard_filter": 0
		   },
		   {
			"fieldname": "status",
			"fieldtype": "Select",
			"label": "PO Status",
			"mandatory": 0,
			"options": "\nTo Receive and Bill\nTo Bill\nTo Receive\nCompleted\nCancelled\nClosed\nOn Hold",
			"wildcard_filter": 0
		   },
		   {
			"fieldname": "item_code",
			"fieldtype": "Link",
			"label": "Item",
			"mandatory": 0,
			"options": "Item",
			"wildcard_filter": 0
		   },
		   {
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"label": "Warehouse",
			"mandatory": 0,
			"options": "Warehouse",
			"wildcard_filter": 0
		   }
	],

	"formatter": function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

		// Formating PR
        if (column.fieldname === "pr_numbers") {
			if (!data || !data.pr_ui_details || data.pr_ui_details.length === 0) {
				return value;
			}

			let final_html = [];
			let temp_div = document.createElement('div');
			temp_div.innerHTML = value;
			let links = Array.from(temp_div.children);

			for (let i = 0; i < data.pr_ui_details.length; i++) {
				let details = data.pr_ui_details[i];
				
				let detail_parts = [];

				if (details.link_html) {detail_parts.push(details.link_html);}
				if (details.date) {detail_parts.push(details.date);}
				if (details.status_html) {detail_parts.push(details.status_html);}
				if (details.qty_html) {detail_parts.push(details.qty_html);}

				final_html.push(`<div>${detail_parts.join(' | ')}</div>`);
				
			}
			return final_html.join('');
		}




		// Formating SE
		if (column.fieldname === "se_numbers") {
			if (!data || !data.se_ui_details || data.se_ui_details.length === 0) {
				return value;
			}

			let final_html = [];
			for (let i = 0; i < data.se_ui_details.length; i++) {
				let details = data.se_ui_details[i];
					let detail_parts = [];
				
				if (details.link_html) {detail_parts.push(details.link_html);}
				if (details.date) {detail_parts.push(details.date);}
				if (details.workflow_html) {detail_parts.push(details.workflow_html);}

				final_html.push(`<div>${detail_parts.join(' | ')}</div>`);
				
			}
			return final_html.join('');
		}

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
