import frappe
from frappe import _
import os
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch, cm
from reportlab.graphics.barcode import code128
import tempfile

@frappe.whitelist()
def download_stock_entry_barcodes(stock_entry_name, stock_entry_detail_name):
    """
    Generate and save barcodes PDF for serial numbers from stock entry detail row
    
    Args:
        stock_entry_name: Name of the Stock Entry document
        stock_entry_detail_name: Name of the Stock Entry Detail row
    """
    try:
        # Validate inputs
        if not stock_entry_name or not stock_entry_detail_name:
            frappe.throw(_("Stock Entry name and Stock Entry Detail name are required"))
        
        # Get stock entry detail
        if not frappe.db.exists("Stock Entry Detail", stock_entry_detail_name):
            frappe.throw(_("Stock Entry Detail {0} not found").format(stock_entry_detail_name))
            
        stock_entry_detail = frappe.get_doc("Stock Entry Detail", stock_entry_detail_name)
        
        if not stock_entry_detail.serial_and_batch_bundle:
            frappe.throw(_("No Serial and Batch Bundle found for this row"))
        
        # Get all serial numbers from the bundle
        serial_numbers = get_serial_numbers_from_bundle(stock_entry_detail.serial_and_batch_bundle)
        
        if not serial_numbers:
            frappe.throw(_("No serial numbers found in the bundle"))
        
        # Generate PDF
        pdf_content = generate_barcode_pdf(serial_numbers, stock_entry_name)
        
        # Create and save file in File doctype
        file_doc = save_pdf_to_file_doctype(
            pdf_content, 
            stock_entry_name, 
            stock_entry_detail_name,
            stock_entry_detail.item_code
        )
        
        return {
            "success": True,
            "message": "Barcode PDF generated successfully",
            "file_url": file_doc.file_url,
            "file_name": file_doc.file_name,
            "download_link": f"/api/method/frappe.core.doctype.file.file.download_file?file_url={file_doc.file_url}"
        }
        
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Error in download_stock_entry_barcodes: {error_msg}", "Barcode Generation Error")
        frappe.throw(_("Error generating barcode PDF: {0}").format(error_msg))

def save_pdf_to_file_doctype(pdf_content, stock_entry_name, stock_entry_detail_name, item_code):
    """
    Save PDF content to File doctype
    
    Args:
        pdf_content: PDF file content as bytes
        stock_entry_name: Stock Entry name for reference
        stock_entry_detail_name: Stock Entry Detail name
        item_code: Item code for better identification
    
    Returns:
        File document
    """
    try:
        # Create unique filename including row name to avoid conflicts between rows
        timestamp = frappe.utils.now_datetime().strftime("%Y%m%d_%H%M%S")
        # Include stock_entry_detail_name to make it unique per row
        filename = f"barcodes_{stock_entry_name}_{item_code}_{stock_entry_detail_name}_{timestamp}.pdf"
        filename = filename.replace("/", "_").replace(" ", "_")  # Clean filename
        
        # Check if file already exists for THIS SPECIFIC ROW and delete it to avoid duplicates
        existing_files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Stock Entry",
                "attached_to_name": stock_entry_name,
                # Include stock_entry_detail_name in the filter to only match this row's files
                "file_name": ["like", f"%barcodes_{stock_entry_name}_{item_code}_{stock_entry_detail_name}%"]
            },
            fields=["name", "file_name"]
        )
        
        # Delete old barcode files for THIS SPECIFIC ROW only
        for old_file in existing_files:
            try:
                frappe.logger().info(f"Deleting old barcode file: {old_file.file_name}")
                frappe.delete_doc("File", old_file.name, ignore_permissions=True)
            except Exception as delete_error:
                frappe.log_error(
                    f"Error deleting old file {old_file.name}: {str(delete_error)}",
                    "Barcode File Deletion Error"
                )
                # Continue even if deletion fails
        
        # Create new File document
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": "Stock Entry",
            "attached_to_name": stock_entry_name,
            "attached_to_field": None,
            "folder": "Home/Attachments",
            "is_private": 0,  # Set to 1 if you want private files
            "content": pdf_content
        })
        
        file_doc.save(ignore_permissions=True)
        frappe.logger().info(f"Successfully created barcode file: {filename} for row {stock_entry_detail_name}")
        
        return file_doc
        
    except Exception as e:
        error_msg = f"Error saving barcode PDF for {stock_entry_detail_name}: {str(e)}"
        frappe.log_error(error_msg, "Barcode PDF Save Error")
        frappe.logger().error(error_msg)
        raise  # Re-raise to be caught by calling function

def get_serial_numbers_from_bundle(bundle_name):
    """
    Get all serial numbers from Serial and Batch Bundle
    
    Args:
        bundle_name: Name of the Serial and Batch Bundle document
        
    Returns:
        List of serial number names
    """
    bundle_entries = frappe.get_all(
        "Serial and Batch Entry",
        filters={"parent": bundle_name},
        fields=["serial_no"],
        order_by="idx"
    )
    
    return [entry.serial_no for entry in bundle_entries if entry.serial_no]

def get_serial_number_details(serial_no_name):
    """
    Get serial number details including custom barcode, item code, warehouse, and batch
    
    Args:
        serial_no_name: Name of the Serial No document
        
    Returns:
        Dictionary with serial number details
    """
    serial_no = frappe.get_doc("Serial No", serial_no_name)
    
    return {
        "name": serial_no.name,
        "item_code": serial_no.item_code,
        "warehouse": serial_no.warehouse,
        "batch_no": getattr(serial_no, 'batch_no', None),  # Get batch number if available
        # "custom_barcode": getattr(serial_no, 'custom_barcode', serial_no.name)  # Use custom_barcode if available, else use name
        "custom_barcode": serial_no.name  # Use custom_barcode if available, else use name
    }

def generate_barcode_pdf(serial_numbers, stock_entry_name):
    """
    Generate PDF with barcodes (1 per page)
    
    Args:
        serial_numbers: List of serial number names
        stock_entry_name: Name of stock entry for reference
        
    Returns:
        PDF file content as bytes
    """
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    temp_filename = temp_file.name
    temp_file.close()
    
    try:
        frappe.logger().info(f"Starting barcode PDF generation for {len(serial_numbers)} serial numbers")
        
        # Create PDF canvas - compact page size for single barcode
        page_width = 3 * inch  # Reduced width
        page_height = 1.7 * inch  # Reduced height for compact label
        c = canvas.Canvas(temp_filename, pagesize=(page_width, page_height))
        
        # Reduced page margins for compact layout
        margin_left = 0.2 * inch
        margin_right = 0.2 * inch
        margin_top = 0.25 * inch
        margin_bottom = 0.25 * inch
        
        # Calculate available space
        available_width = page_width - margin_left - margin_right
        
        # Barcode dimensions - reduced height for shorter serial number barcodes
        barcode_width = available_width  + 1
        barcode_height = 0.6 * inch  # Reduced from 0.8 for shorter barcodes
        
        # Center the barcode vertically on the page
        barcode_y = (page_height - barcode_height) / 2
        
        # Track successful and failed serial numbers
        successful_count = 0
        failed_serials = []
        
        # Process each serial number on its own page
        for idx, serial_no_name in enumerate(serial_numbers):
            if idx > 0:  # Add new page for each barcode after the first
                c.showPage()
            
            try:
                # Get serial number details
                serial_details = get_serial_number_details(serial_no_name)
                
                # Calculate X position to center the barcode
                current_x = margin_left
                
                # Generate barcode using serial number (name)
                barcode_value = serial_details['name']  # Using serial number as barcode
                barcode = code128.Code128(barcode_value, barWidth=1.3, barHeight=barcode_height)
                
                # Scale barcode to fit if needed
                barcode_actual_width = barcode.width
                if barcode_actual_width > barcode_width:
                    scale_factor = barcode_width / barcode_actual_width
                    barcode.barWidth = barcode.barWidth * scale_factor
                
                # Calculate center alignment for barcode
                barcode_x_center = current_x + (barcode_width - barcode.width) / 2
                
                # Draw barcode
                barcode.drawOn(c, barcode_x_center, barcode_y)
                
                # Calculate text center position
                text_center_x = current_x + barcode_width / 2
                
                # Add item code with warehouse above barcode (centered)
                # Format: "MPL100164 - A2_R1_L6"
                c.setFont("Helvetica-Bold", 9)
                warehouse = serial_details.get('warehouse', 'N/A') or 'N/A'
                item_warehouse_text = f"{serial_details['item_code']} - {warehouse}"
                text_width = c.stringWidth(item_warehouse_text, "Helvetica-Bold", 9)
                text_x = text_center_x - (text_width / 2)
                text_y = barcode_y + barcode_height + 12
                c.drawString(text_x, text_y, item_warehouse_text)
                
                # Add batch-serial number below barcode (centered)
                # Format: "Batch-SerialNo" if batch exists, otherwise just "SerialNo"
                c.setFont("Helvetica", 8)
                batch_no = serial_details.get('batch_no')
                if batch_no:
                    serial_text = f"{batch_no} - {serial_details['name']}"
                else:
                    serial_text = f"{serial_details['name']}"
                serial_text_width = c.stringWidth(serial_text, "Helvetica", 8)
                serial_text_x = text_center_x - (serial_text_width / 2)
                serial_text_y = barcode_y - 18
                c.drawString(serial_text_x, serial_text_y, serial_text)
                
                successful_count += 1
                
            except Exception as e:
                error_msg = f"Error processing serial number {serial_no_name}: {str(e)}"
                frappe.logger().error(error_msg)
                frappe.log_error(error_msg, "Barcode PDF Serial Processing Error")
                failed_serials.append(serial_no_name)
                continue

        
        # Save PDF
        c.save()
        
        # Log summary
        frappe.logger().info(f"Barcode PDF generation completed. Success: {successful_count}, Failed: {len(failed_serials)}")
        if failed_serials:
            frappe.logger().warning(f"Failed serial numbers: {', '.join(failed_serials)}")
        
        # Read file content
        with open(temp_filename, 'rb') as f:
            pdf_content = f.read()
        
        return pdf_content
        
    except Exception as e:
        error_msg = f"Critical error generating barcode PDF for {stock_entry_name}: {str(e)}"
        frappe.logger().error(error_msg)
        frappe.log_error(error_msg, "Barcode PDF Generation Critical Error")
        raise
        
    finally:
        # Clean up temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)



import base64

@frappe.whitelist()
def download_row_barcodes(stock_entry_name, row_name):
    """
    Generate barcode PDF for a single Stock Entry Detail row.
    Reads serial data directly from the row's text fields (no bundle/Serial No doc lookup).
    
    Args:
        stock_entry_name: Name of the Stock Entry document
        row_name: Name (internal ID) of the Stock Entry Detail row
        
    Returns:
        dict with base64-encoded PDF content and filename
    """
    if not stock_entry_name or not row_name:
        frappe.throw(_("Stock Entry name and row name are required"))

    # Read the row directly
    row = frappe.db.get_value(
        "Stock Entry Detail",
        row_name,
        ["item_code", "t_warehouse", "batch_no", "serial_no", "serial_and_batch_bundle", "parent"],
        as_dict=True
    )

    if not row:
        frappe.throw(_("Stock Entry Detail row not found"))

    if row.parent != stock_entry_name:
        frappe.throw(_("Row does not belong to the specified Stock Entry"))

    # Fetch serial data using the helper (list of dicts with serial_no and batch_no)
    serial_data = _get_serial_data_from_row(row)

    if not serial_data:
        frappe.throw(_("No valid serial numbers found"))

    # Build base label data from the row
    label_data = {
        "item_code": row.item_code,
        "warehouse": row.t_warehouse or "N/A"
    }

    # Generate the PDF
    pdf_content = generate_barcode_pdf_from_row(serial_data, label_data)

    # Return base64-encoded PDF
    return {
        "pdf_base64": base64.b64encode(pdf_content).decode("utf-8"),
        "filename": f"Barcodes_{row.item_code}_{stock_entry_name}.pdf"
    }


def _get_serial_data_from_row(row):
    """
    Orchestrator to get serial/batch data from either 'serial_no' text field
    or 'serial_and_batch_bundle' link.
    Returns: list of dicts like [{'serial_no': '...', 'batch_no': '...'}, ...]
    """
    if row.get("serial_no"):
        return _get_serials_from_text(row)
    
    if row.get("serial_and_batch_bundle"):
        return _get_serials_from_bundle(row.serial_and_batch_bundle)
    
    return []


def _get_serials_from_text(row):
    """Parse serials from the row's serial_no text field, using the row's batch_no."""
    if not row.serial_no:
        return []
    
    serial_list = [s.strip() for s in row.serial_no.split('\n') if s.strip()]
    return [{"serial_no": s, "batch_no": row.batch_no} for s in serial_list]


def _get_serials_from_bundle(bundle_name):
    """Retrieve serial numbers and their respective batch numbers from a Bundle."""
    if not bundle_name:
        return []
    
    # Query the Serial and Batch Entry child table for both fields
    entries = frappe.get_all(
        "Serial and Batch Entry",
        filters={"parent": bundle_name},
        fields=["serial_no", "batch_no"]
    )
    
    return [{"serial_no": e.serial_no, "batch_no": e.batch_no} for e in entries if e.serial_no]


def generate_barcode_pdf_from_row(serial_data, label_data):
    """
    Generate PDF with barcodes (1 per page) using data passed directly.
    
    Args:
        serial_data: List of dicts [{'serial_no': '...', 'batch_no': '...'}]
        label_data: dict with item_code, warehouse
        
    Returns:
        PDF file content as bytes
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    temp_filename = temp_file.name
    temp_file.close()

    try:
        page_width = 3 * inch
        page_height = 1.7 * inch
        c = canvas.Canvas(temp_filename, pagesize=(page_width, page_height))

        margin_left = 0.2 * inch
        margin_right = 0.2 * inch

        available_width = page_width - margin_left - margin_right
        barcode_width = available_width + 1
        barcode_height = 0.6 * inch
        barcode_y = (page_height - barcode_height) / 2

        for idx, data in enumerate(serial_data):
            serial_no = data.get("serial_no")
            batch_no = data.get("batch_no")

            if not serial_no:
                continue

            if idx > 0:
                c.showPage()

            try:
                current_x = margin_left

                # Barcode value = serial number itself
                barcode = code128.Code128(serial_no, barWidth=1.3, barHeight=barcode_height)

                # Scale barcode to fit if needed
                barcode_actual_width = barcode.width
                if barcode_actual_width > barcode_width:
                    scale_factor = barcode_width / barcode_actual_width
                    barcode.barWidth = barcode.barWidth * scale_factor

                barcode_x_center = current_x + (barcode_width - barcode.width) / 2
                barcode.drawOn(c, barcode_x_center, barcode_y)

                text_center_x = current_x + barcode_width / 2

                # Top label: "item_code - warehouse"
                c.setFont("Helvetica-Bold", 9)
                item_warehouse_text = f"{label_data['item_code']} - {label_data['warehouse']}"
                text_width = c.stringWidth(item_warehouse_text, "Helvetica-Bold", 9)
                text_x = text_center_x - (text_width / 2)
                text_y = barcode_y + barcode_height + 12
                c.drawString(text_x, text_y, item_warehouse_text)

                # Bottom label: "batch_no - serial_no" or just "serial_no"
                c.setFont("Helvetica", 8)
                if batch_no:
                    serial_text = f"{batch_no} - {serial_no}"
                else:
                    serial_text = serial_no
                serial_text_width = c.stringWidth(serial_text, "Helvetica", 8)
                serial_text_x = text_center_x - (serial_text_width / 2)
                serial_text_y = barcode_y - 18
                c.drawString(serial_text_x, serial_text_y, serial_text)

            except Exception as e:
                frappe.log_error(
                    f"Error generating barcode for serial {serial_no}: {str(e)}",
                    "Row Barcode Generation Error"
                )
                continue

        c.save()

        with open(temp_filename, 'rb') as f:
            pdf_content = f.read()

        return pdf_content

    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)