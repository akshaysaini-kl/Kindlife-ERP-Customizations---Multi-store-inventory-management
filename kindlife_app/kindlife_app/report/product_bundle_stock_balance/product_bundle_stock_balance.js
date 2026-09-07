// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Product Bundle Stock Balance"] = {
	"filters": [
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"default": "",
			"description": "Leave blank to use the configured main warehouse"
		},
		{
			"fieldname": "product_bundle",
			"label": __("Product Bundle"),
			"fieldtype": "Link",
			"options": "Product Bundle",
		},
		{
			"fieldname": "show_zero_stock",
			"label": __("Show Zero Stock Bundles"),
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname": "bundle_type",
			"label": __("Bundle Type (B2C/B2B)"),
			"fieldtype": "Select",
			"options": "\nB2C\nB2B\nAll",
			"default": "All"
		}
	],

	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Highlight zero good qty in red
		if (column.fieldname === "good_qty" && data && flt(data.good_qty) === 0) {
			value = `<span style="color: red; font-weight: bold;">${value}</span>`;
		}
		// Highlight low stock (good qty < bundle threshold) in orange
		if (column.fieldname === "good_qty" && data && flt(data.good_qty) > 0 && flt(data.good_qty) <= 10) {
			value = `<span style="color: #e65c00; font-weight: bold;">${value}</span>`;
		}
		// Highlight bottleneck component
		if (column.fieldname === "bottleneck_component" && data && data.bottleneck_component) {
			value = `<span style="color: #7a5200;">${value}</span>`;
		}

		return value;
	}
};
