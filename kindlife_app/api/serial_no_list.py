import frappe
import json
from kindlife_app.api.barcode_download import generate_barcode_pdf,save_pdf_to_file_doctype


@frappe.whitelist()
def generate_barcodes_for_serial_nos():
    #4. As this fn is called using API so we take the serials using form_dict
    selected_serials_str = frappe.form_dict.get('selected_serials')
    serial_numbers_list = json.loads(selected_serials_str)# Read JSON

    # 5. Generate the PDF content in memory
    pdf_content = generate_barcode_pdf(serial_numbers_list, "Bulk-Print")
    # 6. Use frappe inbuilt system to open download popup
    frappe.response['filename'] = f"barcodes-{frappe.utils.nowdate()}.pdf"
    frappe.response['filecontent'] = pdf_content
    frappe.response['type'] = 'download'

