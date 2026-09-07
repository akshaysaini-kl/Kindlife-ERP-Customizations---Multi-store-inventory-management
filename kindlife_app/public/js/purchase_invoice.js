frappe.ui.form.on('Purchase Invoice Item', {
    item_code: function (frm, cdt, cdn) {
        set_supplier_sku(frm, cdt, cdn);
    },
    price_list_rate: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
    },
    custom_list_price: function (frm, cdt, cdn) {
        calculate_custom_margin(cdt, cdn);
    }
});

frappe.ui.form.on('Purchase Invoice', {
    supplier: function (frm) {
        frm.doc.items.forEach((d) => {
            set_supplier_sku(frm, null, null, d);
        });
    },
    refresh: function (frm) {
        set_custom_type_based_on_role(frm);
    }
});


function calculate_custom_margin(cdt, cdn) {
    let row = locals[cdt][cdn];
    let custom_list_price = flt(row.custom_list_price);
    let buyer_price = flt(row.price_list_rate);

    if (custom_list_price > 0 && buyer_price > 0) {
        let margin = ((custom_list_price - buyer_price) / custom_list_price) * 100;
        console.log("margin", margin);
        frappe.model.set_value(cdt, cdn, 'custom_margin', flt(margin, 2));
    } else {
        frappe.model.set_value(cdt, cdn, 'custom_margin', null);
    }
}

function set_supplier_sku(frm, cdt, cdn, row = null) {
    let child = row || locals[cdt][cdn];
    if (!child.item_code || !frm.doc.supplier) return;

    frappe.db.get_doc('Item', child.item_code).then(item_doc => {
        const supplier_item = item_doc.supplier_items.find(s => s.supplier === frm.doc.supplier);
        if (supplier_item) {
            frappe.model.set_value(child.doctype, child.name, 'custom_supplier_sku_code', supplier_item.supplier_part_no);
        } else {
            frappe.model.set_value(child.doctype, child.name, 'custom_supplier_sku_code', '');
        }
    }).catch(error => {
        console.error("Error fetching item details:", error);
        frappe.model.set_value(child.doctype, child.name, 'custom_supplier_sku_code', '');
    });
}