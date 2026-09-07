app_name = "kindlife_app"
app_title = "Kindlife App"
app_publisher = "Auriga IT"
app_description = "Kindlife ERP Customisations"
app_email = "praveen.kumawat@aurigait.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "kindlife_app",
# 		"logo": "/assets/kindlife_app/logo.png",
# 		"title": "Kindlife App",
# 		"route": "/kindlife_app",
# 		"has_permission": "kindlife_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/kindlife_app/css/kindlife_app.css"
app_include_js = [
    "/assets/kindlife_app/js/row_locking_mixin.js",
    "/assets/kindlife_app/js/utils.js",
    "/assets/kindlife_app/js/kindlife_app.js",
    "/assets/kindlife_app/js/global_duplicate_check.js"
]

# include js, css files in header of web template
# web_include_css = "/assets/kindlife_app/css/kindlife_app.css"
# web_include_js = "/assets/kindlife_app/js/kindlife_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "kindlife_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views  
doctype_js = {
    "Purchase Order" : "public/js/purchase_order.js",
    "Purchase Receipt" : "public/js/purchase_receipt.js",
    "Sales Order" : "public/js/sales_order.js",
    "Sales Invoice" : "public/js/sales_invoice.js",
    "Purchase Invoice" : "public/js/purchase_invoice.js",
    "Item" : "public/js/item_master.js",
    "Customer" : "public/js/customer.js",
    "Supplier" : "public/js/supplier.js",
    "Item Group" : "public/js/item_group.js",
    "Customer Group" : "public/js/customer_group.js",
    "Supplier Group" : "public/js/supplier_group.js",
    "Item Price" : "public/js/item.js",
    "Price List" : "public/js/price_list.js",
    "Stock Entry":"public/js/stock_entry.js",
    "Pick List":"public/js/picklist.js",
    "Delivery Note":"public/js/delivery_note.js",
    "Brand":"public/js/brand.js",
    }
doctype_list_js = {
                "Item Price" : "public/js/item.js",
                "Brand": "public/js/brand_list.js",
                "Serial No": "public/js/serial_no_list.js",
                "Pick List": "public/js/pick_list_list.js",
                }
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "kindlife_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

on_login = "kindlife_app.custom_scripts.login.on_login"

# website user home page (by Role)
role_home_page = {
	"Website User": "warehouse-home"
}

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "kindlife_app.utils.jinja_methods",
# 	"filters": "kindlife_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "kindlife_app.install.before_install"
# after_install = "kindlife_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "kindlife_app.uninstall.before_uninstall"
# after_uninstall = "kindlife_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "kindlife_app.utils.before_app_install"
# after_app_install = "kindlife_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "kindlife_app.utils.before_app_uninstall"
# after_app_uninstall = "kindlife_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "kindlife_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways


# This is for role permission based filters in doctypes
permission_query_conditions = {
    "Purchase Order":"kindlife_app.services.permissions.doctypes.purchase_order.permission_query",
    "Purchase Receipt": "kindlife_app.services.permissions.doctypes.purchase_receipt.permission_query",
    "Sales Order": "kindlife_app.services.permissions.doctypes.sales_order.permission_query",
    "Sales Invoice": "kindlife_app.services.permissions.doctypes.sales_invoice.permission_query",
    "Purchase Invoice": "kindlife_app.services.permissions.doctypes.purchase_invoice.permission_query",
    "Stock Entry": "kindlife_app.services.permissions.doctypes.stock_entry.permission_query",
    "Pick List": "kindlife_app.services.permissions.doctypes.pick_list.permission_query",
    "Delivery Note": "kindlife_app.services.permissions.doctypes.delivery_note.permission_query",
    "Warehouse": "kindlife_app.services.permissions.doctypes.warehouse.permission_query",
    "Supplier": "kindlife_app.services.permissions.doctypes.supplier.permission_query",
}


has_permission = {
    "Purchase Order":"kindlife_app.services.permissions.doctypes.purchase_order.has_permission",
    "Purchase Receipt": "kindlife_app.services.permissions.doctypes.purchase_receipt.has_permission",
    "Sales Order": "kindlife_app.services.permissions.doctypes.sales_order.has_permission",
    "Sales Invoice": "kindlife_app.services.permissions.doctypes.sales_invoice.has_permission",
    "Purchase Invoice": "kindlife_app.services.permissions.doctypes.purchase_invoice.has_permission",
    "Stock Entry": "kindlife_app.services.permissions.doctypes.stock_entry.has_permission",
    "Pick List": "kindlife_app.services.permissions.doctypes.pick_list.has_permission",
    "Delivery Note": "kindlife_app.services.permissions.doctypes.delivery_note.has_permission",
    "Warehouse": "kindlife_app.services.permissions.doctypes.warehouse.has_permission",
    "Supplier": "kindlife_app.services.permissions.doctypes.supplier.has_permission",
}

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

override_doctype_class = {
    "Stock Entry": "kindlife_app.custom_scripts.stock_entry.StockEntryExtends",
    "Purchase Receipt": "kindlife_app.custom_scripts.purchase_receipt.PurchaseReceiptExtends",
    "Pick List": "kindlife_app.custom_scripts.pick_list.PickListExtends",
    # "Stock Ledger Entry": "kindlife_app.monkey_patches.stock_ledger_entry_override.StockLedgerEntryExtends",
    
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Item Price": {
		"validate": ["kindlife_app.custom_scripts.item_price.item_price_validate"],
		"after_insert": ["kindlife_app.custom_scripts.item_price.set_wokflow_state"],
		
	},
     "Purchase Invoice": {
        "validate": "kindlife_app.custom_scripts.purchase_invoice.validate",
        "on_update_after_submit":"kindlife_app.custom_scripts.purchase_invoice.validate"
    },
    "Purchase Order": {
        "validate":"kindlife_app.custom_scripts.purchase_order.validate",
        "on_update_after_submit":"kindlife_app.custom_scripts.purchase_order.validate",
        "on_update": "kindlife_app.custom_scripts.purchase_order.po_supplier_notification",
        "on_trash": "kindlife_app.custom_scripts.purchase_order.before_purchase_order_trash"
    },
    "Purchase Receipt": {
        "on_submit":"kindlife_app.api.purchase_receipt.purchase_return_on_submit",
    },
    "Item":{
        "before_insert": "kindlife_app.custom_scripts.item.before_insert",
        "validate":"kindlife_app.custom_scripts.item.validate",
        "on_update":"kindlife_app.custom_scripts.item.on_update",
    },
    "Batch": {
        "before_insert": "kindlife_app.custom_scripts.batch.autoname_batch"
    },
    "Sales Order":{
        "validate": ["kindlife_app.custom_scripts.sales_order.so_validate","kindlife_app.services.margin_engine.on_sales_order_submit"],
        # "on_submit": "kindlife_app.services.margin_engine.on_sales_order_submit"
    },
    "Sales Invoice":{
        "before_insert": "kindlife_app.custom_scripts.sales_invoice.set_series_for_return",
        "validate": "kindlife_app.custom_scripts.sales_invoice.validate"
    },
    "Warehouse": {
        "autoname": "kindlife_app.custom_scripts.warehouse.autoname_based_on_parent"
    },
    "Pick List": {
        "before_save": "kindlife_app.custom_scripts.pick_list.before_save",
        "before_submit": "kindlife_app.custom_scripts.pick_list.warn_multiple_sales_orders_on_submit",
        "on_submit": "kindlife_app.custom_scripts.pick_list.validate_batch_numbers_on_submit",
        "after_insert": "kindlife_app.custom_scripts.inventory_sync.on_pick_list_change",
        "on_cancel": "kindlife_app.custom_scripts.inventory_sync.on_pick_list_change"
    },
    "Delivery Note": {
        "before_validate": "kindlife_app.custom_scripts.delivery_note.validate"
    },
    "Stock Ledger Entry": {
        "on_update_after_submit": "kindlife_app.custom_scripts.inventory_sync.on_stock_ledger_entry_submit",
        "on_submit": "kindlife_app.custom_scripts.inventory_sync.on_stock_ledger_entry_submit",
    },
    # Duplicate Detection Hooks
    "Item Group": {
        "validate": "kindlife_app.utils.validation_hooks.validate_item_group_duplicate",
        "before_rename": "kindlife_app.utils.validation_hooks.validate_before_rename",
        "after_insert": "kindlife_app.utils.validation_hooks.set_workflow_state_after_insert",
        "on_update": "kindlife_app.utils.validation_hooks.clear_cache_on_update",
        "on_trash": "kindlife_app.utils.validation_hooks.clear_cache_on_update"
    },
    "Customer Group": {
        "validate": "kindlife_app.utils.validation_hooks.validate_customer_group_duplicate",
        "before_rename": "kindlife_app.utils.validation_hooks.validate_before_rename",
        "after_insert": "kindlife_app.utils.validation_hooks.set_workflow_state_after_insert",
        "on_update": "kindlife_app.utils.validation_hooks.clear_cache_on_update",
        "on_trash": "kindlife_app.utils.validation_hooks.clear_cache_on_update"
    },
    "Brand": {
        "validate": "kindlife_app.utils.validation_hooks.validate_brand_duplicate",
        "before_rename": "kindlife_app.utils.validation_hooks.validate_before_rename",
        "after_insert": "kindlife_app.utils.validation_hooks.set_workflow_state_after_insert",
        "on_update": "kindlife_app.utils.validation_hooks.clear_cache_on_update",
        "on_trash": "kindlife_app.utils.validation_hooks.clear_cache_on_update"
    },
    "Supplier Group": {
        "validate": "kindlife_app.utils.validation_hooks.validate_supplier_group_duplicate",
        "before_rename": "kindlife_app.utils.validation_hooks.validate_before_rename",
        "after_insert": "kindlife_app.utils.validation_hooks.set_workflow_state_after_insert",
        "on_update": "kindlife_app.utils.validation_hooks.clear_cache_on_update",
        "on_trash": "kindlife_app.utils.validation_hooks.clear_cache_on_update"
    },
    "Supplier": {
        "before_save": "kindlife_app.custom_scripts.supplier.before_save"
    },
    "Customer": {
        "before_save": "kindlife_app.custom_scripts.customer.before_save"
    },
    "Product Bundle": {
        "on_update": "kindlife_app.custom_scripts.item.on_update_product_bundle"
    },
    "Stock Entry": {
        "before_save": "kindlife_app.custom_scripts.stock_entry.before_save"
    },

}

# Scheduled Tasks
# ---------------
# ---------------
scheduler_events = {
    "daily": [
        "kindlife_app.kindlife_app.doctype.item_mrp.item_mrp.apply_pending_mrp",
        "kindlife_app.api.brand_fulfillment.create_purchase_orders_for_brand_items",
        "kindlife_app.services.debit_note_engine.daily_debit_note_check",
        "kindlife_app.services.debit_note_engine.daily_warehouse_debit_note_check"
    ],
    "cron": {
        "0 */2 * * *": [
            "kindlife_app.api.shipment_notification.send_shipment_notifications_to_suppliers"
        ]
    }
}

# Search for 'assistant_tools' or add it at the end
assistant_tools = [
    "kindlife_app.assistant_tools.get_item_by_buyer_sku.GetItemByBuyerSku",
    "kindlife_app.assistant_tools.get_doctype_schema.GetDoctypeSchema"
]


# scheduler_events = {
# 	"all": [
# 		"kindlife_app.tasks.all"
# 	],
# 	"daily": [
# 		"kindlife_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"kindlife_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"kindlife_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"kindlife_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "kindlife_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
    "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice":"kindlife_app.custom_scripts.purchase_order.make_purchase_invoice",
    "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_stock_entry":"kindlife_app.custom_scripts.purchase_receipt.make_stock_entry",
    "erpnext.stock.doctype.putaway_rule.putaway_rule.apply_putaway_rule":"kindlife_app.custom_scripts.putaway_rule.apply_putaway_rule",
    "erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return":"kindlife_app.custom_scripts.sales_invoice.custom_make_sales_return",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Item": "kindlife_app.custom_scripts.item.get_item_dashboard_data"
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["kindlife_app.utils.before_request"]
# after_request = ["kindlife_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["kindlife_app.utils.before_job"]
# after_job = ["kindlife_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"kindlife_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }