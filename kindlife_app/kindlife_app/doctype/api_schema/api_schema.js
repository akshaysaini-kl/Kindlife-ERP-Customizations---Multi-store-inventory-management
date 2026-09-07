// Copyright (c) 2024, Kindlife and contributors
// For license information, please see license.txt

frappe.ui.form.on('API Schema', {
    refresh: function (frm) {
        if (frm.doc.reference_doctype) {
            frm.add_custom_button(__('Pick Fields'), function () {
                fetch_fields_and_show_dialog(frm);
            });
        }
    },
    reference_doctype: function (frm) {
        if (frm.doc.reference_doctype) {
            frm.add_custom_button(__('Pick Fields'), function () {
                fetch_fields_and_show_dialog(frm);
            });
        }
    }
});

function fetch_fields_and_show_dialog(frm) {
    frappe.model.with_doctype(frm.doc.reference_doctype, function () {
        let meta = frappe.get_meta(frm.doc.reference_doctype);
        // Get standard fields
        let standard_fields = [
            { fieldname: 'name', label: 'ID', fieldtype: 'Data' },
            { fieldname: 'owner', label: 'Owner', fieldtype: 'Data' },
            { fieldname: 'creation', label: 'Created On', fieldtype: 'Datetime' },
            { fieldname: 'modified', label: 'Last Modified On', fieldtype: 'Datetime' },
            { fieldname: 'idx', label: 'Index', fieldtype: 'Int' }
        ];

        // Filter out layout fields like Section Break, etc.
        let fields = meta.fields.filter(f =>
            !['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button', 'Image'].includes(f.fieldtype)
        );

        let all_fields = [...standard_fields, ...fields];

        let d = new frappe.ui.Dialog({
            title: __('Select Fields'),
            fields: [
                {
                    label: "Fields",
                    fieldname: "fields",
                    fieldtype: "MultiCheck",
                    options: all_fields.map(f => ({
                        label: `${f.label} (${f.fieldname})`,
                        value: f.fieldname,
                        checked: 0
                    })),
                    columns: 2
                }
            ],
            primary_action_label: __('Add Selected'),
            primary_action: function () {
                let data = d.get_values();
                if (data && data.fields) {
                    data.fields.forEach(fieldname => {
                        // Check if already exists
                        let exists = frm.doc.schema_fields.some(row => row.source_field === fieldname);
                        if (!exists) {
                            let field = all_fields.find(f => f.fieldname === fieldname);
                            let row = frm.add_child('schema_fields');
                            row.source_field = field.fieldname;
                            row.source_label = field.label;
                            row.target_key = field.fieldname; // Default to fieldname
                        }
                    });
                    frm.refresh_field('schema_fields');
                }
                d.hide();
            }
        });
        d.show();
    });
}
