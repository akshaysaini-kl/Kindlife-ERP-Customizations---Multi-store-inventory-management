function get_currency_symbol(currency) {
	if (frappe.boot) {
		if (frappe.boot.sysdefaults && frappe.boot.sysdefaults.hide_currency_symbol == "Yes")
			return null;

		if (!currency) currency = frappe.boot.sysdefaults.currency;

		return frappe.model.get_value(":Currency", currency, "symbol") || currency;
        
	} else {
// 		// load in template
		return frappe.currency_symbols[currency];
	}
}
