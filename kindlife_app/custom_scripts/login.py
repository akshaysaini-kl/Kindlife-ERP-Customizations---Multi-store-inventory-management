import frappe

def on_login(login_manager):
    
    # Get user roles
    user_roles = frappe.db.get_all(
        'Has Role',
        filters={'parent': login_manager.user, 'parenttype': 'User'},
        pluck='role'
    )
    role_profile = frappe.db.get_value("User", {"name": login_manager.user}, "role_profile_name")

    # Check if user has Warehouse User role
    if "Warehouse User" in user_roles:
        frappe.local.flags.redirect_location = "/warehouse-home"
    
    # Check role profile for other redirections
    elif role_profile == 'Technician':
        frappe.local.flags.redirect_location = "/home"
    elif role_profile == 'Purchasing Team':
        frappe.local.flags.redirect_location = "/links"
    else:
        frappe.local.flags.redirect_location = "/menu"


    # Here the report table schema is stored according to roles.
    values = {
        "Warehouse User":[
            {
                'data': '{"updated_on":"Fri Nov 14 2025 16:29:55 GMT+0530","last_view":"Report","List":{"filters":[],"sort_by":"modified","sort_order":"desc"},"Report":{"filters":[],"sort_by":"modified","sort_order":"desc","fields":[["name","Purchase Order"],["docstatus","Purchase Order"],["workflow_state","Purchase Order"],["total_qty","Purchase Order"],["supplier","Purchase Order"],["custom_type","Purchase Order"],["transaction_date","Purchase Order"],["per_received","Purchase Order"]],"order_by":"`tabPurchase Order`.`modified` desc","group_by":null,"add_totals_row":0}}',
                'user': login_manager.user,
                'doctype': 'Purchase Order'
            },
            {
                'data': '{"updated_on":"Fri Nov 14 2025 16:58:59 GMT+0530","last_view":"Report","List":{"filters":[],"sort_by":"modified","sort_order":"desc"},"Report":{"fields":[["name","Purchase Receipt"],["total_qty","Purchase Receipt"],["docstatus","Purchase Receipt"],["workflow_state","Purchase Receipt"],["supplier","Purchase Receipt"],["custom_type","Purchase Receipt"],["posting_date","Purchase Receipt"],["per_returned","Purchase Receipt"]],"filters":[],"order_by":"`tabPurchase Receipt`.`modified` desc","group_by":null,"add_totals_row":0,"sort_by":"modified","sort_order":"desc"}}',
                'user': login_manager.user,
                'doctype': 'Purchase Receipt'
            },
            {
                'data': '{"updated_on":"Wed Nov 19 2025 22:50:28 GMT+0530","last_view":"Report","Report":{"fields":[["workflow_state","Sales Order"],["name","Sales Order"],["docstatus","Sales Order"],["total_qty","Sales Order"],["custom_type","Sales Order"],["delivery_date","Sales Order"],["po_no","Sales Order"],["per_picked","Sales Order"],["customer","Sales Order"],["per_delivered","Sales Order"]],"filters":[],"order_by":"`tabSales Order`.`modified` desc","group_by":null,"add_totals_row":0,"sort_by":"modified","sort_order":"desc"},"List":{"filters":[],"sort_by":"modified","sort_order":"desc"},"Dashboard":{}}',
                'user': login_manager.user,
                'doctype': 'Sales Order'
            },
        ],
        "Others":[
            {
                'data': '{"updated_on":"Fri Nov 14 2025 16:32:14 GMT+0530","last_view":"Report","List":{"filters":[],"sort_by":"modified","sort_order":"desc"},"Report":{"filters":[],"sort_by":"modified","sort_order":"desc","fields":[["workflow_state","Purchase Order"],["name","Purchase Order"],["docstatus","Purchase Order"],["total_qty","Purchase Order"],["supplier","Purchase Order"],["custom_type","Purchase Order"],["transaction_date","Purchase Order"],["grand_total","Purchase Order"],["per_received","Purchase Order"],["per_billed","Purchase Order"],["buying_price_list","Purchase Order"]],"order_by":"`tabPurchase Order`.`modified` desc","group_by":null,"add_totals_row":0}}',
                'user': login_manager.user,
                'doctype': 'Purchase Order'
            },
            {
                'data': '{"updated_on":"Fri Nov 14 2025 17:01:05 GMT+0530","last_view":"Report","List":{"filters":[],"sort_by":"modified","sort_order":"desc"},"Report":{"fields":[["name","Purchase Receipt"],["posting_date","Purchase Receipt"],["docstatus","Purchase Receipt"],["total_qty","Purchase Receipt"],["supplier","Purchase Receipt"],["custom_type","Purchase Receipt"],["workflow_state","Purchase Receipt"],["per_returned","Purchase Receipt"],["per_billed","Purchase Receipt"],["buying_price_list","Purchase Receipt"],["grand_total","Purchase Receipt"]],"filters":[],"order_by":"`tabPurchase Receipt`.`modified` desc","group_by":null,"add_totals_row":0,"sort_by":"modified","sort_order":"desc"}}',
                'user': login_manager.user,
                'doctype': 'Purchase Receipt'
            },
            {
                'data': '{"updated_on":"Wed Nov 19 2025 22:50:28 GMT+0530","last_view":"Report","Report":{"fields":[["workflow_state","Sales Order"],["name","Sales Order"],["docstatus","Sales Order"],["total_qty","Sales Order"],["grand_total","Sales Order"],["custom_type","Sales Order"],["delivery_date","Sales Order"],["po_no","Sales Order"],["per_billed","Sales Order"],["per_picked","Sales Order"],["per_delivered","Sales Order"],["taxes_and_charges","Sales Order"],["customer","Sales Order"]],"filters":[],"order_by":"`tabSales Order`.`modified` desc","group_by":null,"add_totals_row":0,"sort_by":"modified","sort_order":"desc"},"List":{"filters":[],"sort_by":"modified","sort_order":"desc"},"Dashboard":{}}',
                'user': login_manager.user,
                'doctype': 'Sales Order'
            },
        ]
    }

    # This looks for the number of times a user has logged in to our system
    # We want that the report tables should be updated only when a user logges in for first time
    activity_count = frappe.db.count('Activity Log', {'user': login_manager.user, 'operation': 'Login', 'status': 'Success'})
    if activity_count == 0:
        settings_to_apply = values["Others"]
        if "Warehouse User" in user_roles:
            settings_to_apply = values["Warehouse User"]


        for value in settings_to_apply:
            frappe.db.sql("""INSERT INTO `__UserSettings` (`user`, `doctype`, `data`)VALUES (%(user)s, %(doctype)s, %(data)s)ON DUPLICATE KEY UPDATE `data` = %(data)s """, values=value, as_dict=0)
                
        frappe.clear_cache(user=login_manager.user)

