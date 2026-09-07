import frappe
from kindlife_app.custom_scripts.utils import update_gst_hsn_code
from frappe.utils import get_url
from frappe.email.doctype.notification.notification import get_context
from erpnext.buying.doctype.purchase_order.purchase_order import set_missing_values
from erpnext.accounts.party import get_party_account
from frappe.utils import flt
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from frappe.model.mapper import get_mapped_doc
import json
from kindlife_app.utils.shipment_utils import sync_shipment_docs_for_doc


def validate(doc,method):
    # if(doc.workflow_state =="Approved"):
    #     if not doc.custom_signature or not doc.custom_stamp:
    #         frappe.throw("Please make sure to fill signature and stamp field")
    #     if doc.custom_signature != frappe.session.user:
    #         frappe.throw("Please make sure that the Signature selected belong to the person who is approving the Purchase order")

    update_gst_hsn_code(doc)
    update_customer(doc)
    sync_shipment_docs_for_doc(doc, "sales_order")



def update_customer(doc):
    custom_alias = None
    
    for item in doc.items:
        if item.sales_order:
            so_doc = frappe.get_doc("Sales Order", item.sales_order)
            custom_alias = so_doc.custom_alias
            break  # Take the first sales order's customer
    
    doc.custom_alias = custom_alias or ''


def po_supplier_notification(doc, method):
    # This function is triggered on Update (on_update hook)
    if doc.workflow_state != "Approved":
        return

    try:
        if not doc.contact_person:
            frappe.log_error(
                message=f"No contact person selected for Purchase Order {doc.name}. Supplier: {doc.supplier_name or doc.supplier}",
                title="PO Notification Skip: Missing Contact"
            )
            return

        # Select template based on custom_type
        template_name = "PO B2B" if doc.custom_type == "B2B" else "PO Dropship"
        
        try:
            notification = frappe.get_doc("Notification", template_name)
        except frappe.DoesNotExistError:
            frappe.log_error(
                message=f"Notification Template '{template_name}' not found for Purchase Order {doc.name}. Supplier: {doc.supplier_name or doc.supplier}",
                title="PO Notification Error: Template Missing"
            )
            return

        # Get recipients
        email_ids = frappe.get_all("Contact Email", filters={"parent": doc.contact_person}, fields=["email_id"])
        recipient_emails = [e["email_id"] for e in email_ids if e["email_id"]]

        if not recipient_emails:
            frappe.log_error(
                message=f"No email addresses found for Contact {doc.contact_person} on Purchase Order {doc.name}. Supplier: {doc.supplier_name or doc.supplier}",
                title="PO Notification Error: No Recipients"
            )
            return

        # Prepare attachments: Initial with PO PDF
        attachments = []
        try:
            print_format = "Drop Shipping Format" if doc.custom_type != "B2B" else None
            po_pdf = frappe.attach_print(doc.doctype, doc.name, print_format=print_format, file_name=f"Purchase Order {doc.name}.pdf")
            if po_pdf:
                attachments.append(po_pdf)
        except Exception as e:
            frappe.log_error(
                message=f"Failed to generate PO PDF for {doc.name}: {str(e)}",
                title="PO Notification: PDF Generation Error"
            )


        # Render subject and message
        ctx = get_context(doc)
        subject = frappe.render_template(notification.subject, ctx)
        message = frappe.render_template(notification.message, ctx)

        # Send email
        frappe.sendmail(
            recipients=recipient_emails,
            subject=subject,
            message=message,
            attachments=attachments,
            reference_doctype=doc.doctype,
            reference_name=doc.name
        )
    except Exception as e:
        frappe.log_error(
            message=f"Total failure in PO notification for {doc.name}. Supplier: {doc.supplier_name or doc.supplier}. Error: {str(e)}\n{frappe.get_traceback()}",
            title="PO Notification: Critical Failure"
        )



@frappe.whitelist()
def make_purchase_invoice(source_name, target_doc=None,args=None):
    print("here-----")
    return get_mapped_purchase_invoice(source_name, target_doc,args=args)


def get_mapped_purchase_invoice(source_name, target_doc=None, ignore_permissions=False,args=None):
    if args is None:
        args = {}
    if isinstance(args, str):
        args = json.loads(args)

    print("hereee")
    def postprocess(source, target):
        target.flags.ignore_permissions = ignore_permissions
        set_missing_values(source, target)

        # set tax_withholding_category from Purchase Order
        if source.apply_tds and source.tax_withholding_category and target.apply_tds:
            target.tax_withholding_category = source.tax_withholding_category

        # Get the advance paid Journal Entries in Purchase Invoice Advance
        if target.get("allocate_advances_automatically"):
            target.set_advances()

        target.set_payment_schedule()
        target.credit_to = get_party_account("Supplier", source.supplier, source.company)

    def update_item(obj, target, source_parent):
        target.amount = flt(obj.amount) - flt(obj.billed_amt)
        target.base_amount = target.amount * flt(source_parent.conversion_rate)
        target.qty = (
            target.amount / flt(obj.rate) if (flt(obj.rate) and flt(obj.billed_amt)) else flt(obj.qty)
        )

        item = get_item_defaults(target.item_code, source_parent.company)
        item_group = get_item_group_defaults(target.item_code, source_parent.company)
        target.cost_center = (
            obj.cost_center
            or frappe.db.get_value("Project", obj.project, "cost_center")
            or item.get("buying_cost_center")
            or item_group.get("buying_cost_center")
        )



    def select_item(d):
        filtered_items = args.get("filtered_children", [])
        child_filter = d.name in filtered_items if filtered_items else True
        return child_filter


    fields = {
        "Purchase Order": {
            "doctype": "Purchase Invoice",
            "field_map": {
                "party_account_currency": "party_account_currency",
                "supplier_warehouse": "supplier_warehouse",
            },
            "field_no_map": ["payment_terms_template"],
            "validation": {
                "docstatus": ["=", 1],
            },
        },
        "Purchase Order Item": {
            "doctype": "Purchase Invoice Item",
            "field_map": {
                "name": "po_detail",
                "parent": "purchase_order",
                "material_request": "material_request",
                "material_request_item": "material_request_item",
                "wip_composite_asset": "wip_composite_asset",
                "custom_list_price":"custom_list_price",
                "custom_margin":"custom_margin"
            },
            "postprocess": update_item,
            "condition": lambda doc: (doc.base_amount == 0 or abs(doc.billed_amt) < abs(doc.amount)) 
            and select_item(doc),
        },
        "Purchase Taxes and Charges": {"doctype": "Purchase Taxes and Charges", "reset_value": True},
    }

    doc = get_mapped_doc(
        "Purchase Order",
        source_name,
        fields,
        target_doc,
        postprocess,
        ignore_permissions=ignore_permissions,
    )

    return doc


def before_purchase_order_trash(doc, method):
    # Unlink this PO from any Sales Order Items
    frappe.db.set_value("Sales Order Item", {"purchase_order": doc.name}, "purchase_order", None)
