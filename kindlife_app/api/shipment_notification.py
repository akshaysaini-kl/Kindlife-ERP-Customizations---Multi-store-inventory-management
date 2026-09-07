import frappe
from frappe import _

@frappe.whitelist()
def send_shipment_notifications_to_suppliers():
    """
    Scheduled task (Daily Cron)
    1. Finds items in Submitted POs that have shipment documents but haven't been shared.
    2. Groups them by Supplier.
    3. Sends one email per supplier with all pending PDF attachments.
    4. Marks the items as shared.
    """
    try:
        # 1. Fetch pending items
        pending_items = frappe.get_all("Purchase Order Item",
            filters={
                "docstatus": 1,
                "custom_shipment_document": ["is", "set"],
                "custom_shipment_pdf_shared_with_supplier": 0
            },
            fields=["name", "parent", "item_code", "item_name", "qty", "custom_shipment_document"]
        )

        if not pending_items:
            return

        # 2. Group by Supplier and then by Purchase Order
        # supplier_map = { recipient_email: { "supplier_name": str, "po_groups": { po_name: [item_strings] }, "docs": set(), "row_ids": [] } }
        supplier_map = {}
        
        for item in pending_items:
            po_data = frappe.db.get_value("Purchase Order", item.parent, ["supplier", "contact_person"], as_dict=True)
            if not po_data:
                continue

            # Get Supplier Email
            recipient_email = None
            if po_data.contact_person:
                email_list = frappe.get_all("Contact Email", filters={"parent": po_data.contact_person}, fields=["email_id"])
                if email_list:
                    recipient_email = email_list[0].email_id

            if not recipient_email:
                recipient_email = frappe.db.get_value("Supplier", po_data.supplier, "email_id")

            if not recipient_email:
                frappe.log_error(
                    message=f"No email found for Supplier {po_data.supplier} to send shipment PDFs for item {item.name}",
                    title="Shipment Notification Error: Missing Email"
                )
                continue

            if recipient_email not in supplier_map:
                supplier_map[recipient_email] = {
                    "supplier_name": po_data.supplier,
                    "po_groups": {}, 
                    "docs": set(),
                    "row_ids": []
                }
            
            po_name = item.parent
            if po_name not in supplier_map[recipient_email]["po_groups"]:
                supplier_map[recipient_email]["po_groups"][po_name] = []
            
            item_desc = f"{item.item_code} - {item.item_name} (Qty: {item.qty})"
            supplier_map[recipient_email]["po_groups"][po_name].append(item_desc)
            supplier_map[recipient_email]["docs"].add(item.custom_shipment_document)
            supplier_map[recipient_email]["row_ids"].append(item.name)

        # 3. Send emails
        for email, data in supplier_map.items():
            try:
                attachments = []
                for doc_url in data["docs"]:
                    try:
                        file_doc = frappe.get_doc("File", {"file_url": doc_url})
                        attachments.append({
                            "fname": file_doc.file_name,
                            "fcontent": file_doc.get_content()
                        })
                    except Exception as fe:
                        frappe.log_error(f"Failed to attach file {doc_url}: {str(fe)}", "Shipment Notification attachment error")

                if not attachments:
                    continue

                # Build HTML Table for items
                table_rows = ""
                for po_name, items in data["po_groups"].items():
                    item_list_html = "".join([f"<li>{it}</li>" for it in items])
                    table_rows += f"""
                        <tr>
                            <td style="padding: 8px; border: 1px solid #dee2e6; vertical-align: top;">{po_name}</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6;">
                                <ul style="margin: 0; padding-left: 20px;">{item_list_html}</ul>
                            </td>
                        </tr>
                    """

                message = f"""
                    <p>Dear {data['supplier_name']},</p>
                    <p>Please find attached the <strong>shipment labels (PDFs)</strong> for your pending orders on Kindlife. These labels should be used to fulfill the orders listed below.</p>
                    
                    <table border="1" style="border-collapse: collapse; width: 100%; text-align: left; font-family: sans-serif; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th style="padding: 8px; border: 1px solid #dee2e6;">Purchase Order</th>
                                <th style="padding: 8px; border: 1px solid #dee2e6;">Items to be Labeled</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>

                    <p><strong>Instructions:</strong></p>
                    <ul>
                        <li>Attach the printed PDF labels to the correct packages.</li>
                        <li>Ensure no pricing or external branding is included (Blind Dropship).</li>
                    </ul>

                    <p>Thank you!</p>
                    <p>Best regards,<br>Kindlife Fulfillment Team</p>
                """

                frappe.sendmail(
                    recipients=[email],
                    subject=_("Action Required: Shipment Labels Ready - Kindlife"),
                    message=message,
                    attachments=attachments
                )

                # 4. Mark as shared
                for row_id in data["row_ids"]:
                    frappe.db.set_value("Purchase Order Item", row_id, "custom_shipment_pdf_shared_with_supplier", 1, update_modified=False)
                
                frappe.db.commit()

            except Exception as e:
                frappe.log_error(f"Failed to send shipment summary to {email}: {str(e)}", "Shipment Notification Cron Error")

    except Exception as ge:
        frappe.log_error(frappe.get_traceback(), "Shipment Notification Global Cron Error")
