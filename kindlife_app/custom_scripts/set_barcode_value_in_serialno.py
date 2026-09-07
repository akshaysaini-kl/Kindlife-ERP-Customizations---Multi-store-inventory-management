# We have added a custom barcode field in the Serial No doctype.
# This script sets the custom barcode value for each serial number in the Serial and Batch Bundle.

# The barcode is a combination of the warehouse and the serial number.

# This script is triggered on the submission of a Purchase Receipt document.
# It iterates through each item in the Purchase Receipt, checks if it has a Serial and
# Batch Bundle, and then sets the custom barcode for each serial number in that bundle.

# IMPORTANT
# Normally the barcode field stores the svg of the barcode. It dose not store text value.
# So if we fetch the value of barcode field, it will return svg.
# However, here, as we are directly saving the text value to the database, it will store the text value only.
# I have tried to store the svg but it didnt work.


import frappe

def set_serial_custom_barcodes(doc, method):
    # Go to bundle of each item
    for item in doc.items:
        if not item.serial_and_batch_bundle:
            continue

        bundle = frappe.get_doc("Serial and Batch Bundle", item.serial_and_batch_bundle)
        # Iterate over each entry in the bundle
        for entry in bundle.entries:
            serial = entry.serial_no
            warehouse = entry.warehouse
            barcode_value = warehouse + " - " + serial
            if not serial and not warehouse:
                continue

            # Fit value of barcode field in Serial No
            row = frappe.get_doc("Serial No", serial)
            if not row.custom_barcode:
                frappe.db.set_value("Serial No", serial, "custom_barcode", barcode_value)
