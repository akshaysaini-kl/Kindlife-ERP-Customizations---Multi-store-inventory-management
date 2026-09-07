// Copyright (c) 2026, Kindlife and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Kindlife COGS Analysis"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "custom_type",
            "label": __("Business Type"),
            "fieldtype": "Select",
            "options": ["", "B2B", "B2C"],
            "default": ""
        },
        {
            "fieldname": "item_code",
            "label": __("Item"),
            "fieldtype": "Link",
            "options": "Item"
        },
        {
            "fieldname": "fulfillment_type",
            "label": __("Fulfillment Type"),
            "fieldtype": "Select",
            "options": ["", "Warehouse", "Brand"],
            "default": ""
        },
        {
            "fieldname": "customer",
            "label": __("Customer"),
            "fieldtype": "Link",
            "options": "Customer"
        }
    ],
    "get_total_row": function (data) {
        let total_qty = 0.0;
        let total_revenue = 0.0;
        let total_cogs = 0.0;
        let total_gross_margin = 0.0;

        for (let row of data) {
            total_qty += flt(row.qty);
            total_revenue += flt(row.revenue); // Net Revenue
            total_cogs += flt(row.cogs);
            total_gross_margin += flt(row.gross_margin);
        }

        // Calculate Margin % on Inclusive Basis
        // Revenue (Inc Tax) = Gross Margin + COGS
        let total_revenue_inc_tax = total_gross_margin + total_cogs;
        let total_gross_margin_pct = total_revenue_inc_tax ? (total_gross_margin / total_revenue_inc_tax * 100) : 0.0;

        return {
            "sales_invoice": "Total",
            "qty": total_qty,
            "revenue": total_revenue,
            "cogs": total_cogs,
            "gross_margin": total_gross_margin,
            "gross_margin_pct": total_gross_margin_pct
        };
    }
};
