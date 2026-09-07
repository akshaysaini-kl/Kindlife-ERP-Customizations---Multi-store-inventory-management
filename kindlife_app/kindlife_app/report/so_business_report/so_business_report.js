// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt
let validate_dates = function(changed_field) {
	let from_date = frappe.query_report.get_filter_value('from_date');
	let to_date = frappe.query_report.get_filter_value('to_date');
	if (from_date && to_date && from_date > to_date) {
		if (changed_field === 'from_date') {
			frappe.msgprint(__("From Date cannot be after To Date"));
			frappe.query_report.set_filter_value('from_date', to_date);
		} else {
			frappe.msgprint(__("To Date cannot be before From Date"));
			frappe.query_report.set_filter_value('to_date', from_date);
		}
	}
	frappe.query_report.refresh();
};

frappe.query_reports["SO Business Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 1,
			"on_change": () => validate_dates('from_date')
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1,
			"on_change": () => validate_dates('to_date')
		},
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer"
		},
		{
			fieldname: "business_type",
			label: __("Business Type"),
			fieldtype: "Select",
			options: ["B2B", "B2C", "Both"],
			default: "B2B"
		}
	]
};
