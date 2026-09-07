# my_custom_app/my_custom_app/overrides/sales_invoice.py
import frappe

# my_custom_app/my_custom_app/overrides/sales_invoice.py
import frappe

# We must import the original function so that we can call it.
# We give it an alias to avoid any naming confusion.
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return as original_make_sales_return

@frappe.whitelist()
def custom_make_sales_return(source_name, target_doc=None):
    """
    This replaces the oiginal wrape that is called when the credit note button is clicked.
    The only addition is, now before returning the fn, we add a minor change of our own that sets the naming series
    """
    return_doc = original_make_sales_return(source_name, target_doc)
    return_doc.naming_series = "CN-.####"
    return return_doc

def set_series_for_return(doc, method):
    """
        This function will be used for data import and api calls.
        It is called in beofre insert
    """
    if doc.is_return:
        doc.naming_series = "CN-.####"

def validate(doc, method):
    calculate_custom_totals(doc)

def calculate_custom_totals(doc):
    """
    Calculate custom_total_buying_price_without_discount for each item
    and custom_total_without_discount for the parent doc.
    - Also custom_amount_with_gst for each item
    """
    total_without_discount = 0
    for item in doc.items:
        # Calculate conversion factor from taxes
        igst = frappe.utils.flt(item.igst_rate)
        cgst = frappe.utils.flt(item.cgst_rate)
        sgst = frappe.utils.flt(item.sgst_rate)
        # We can either have igst or cgst/sgst
        conversion_factor = (igst + cgst + sgst) / 100.0

        # Calculate using the new formula
        try:
             item.custom_total_buying_price_without_discount = (frappe.utils.flt(item.price_list_rate) * frappe.utils.flt(item.qty)) / (1 + conversion_factor)
        except ZeroDivisionError:
             item.custom_total_buying_price_without_discount = (frappe.utils.flt(item.price_list_rate) * frappe.utils.flt(item.qty))

        # (custom_list_price * qty)*(1-custom_margin)
        custom_list_price = frappe.utils.flt(item.custom_list_price)
        qty = frappe.utils.flt(item.qty)
        custom_margin = frappe.utils.flt(item.custom_margin)
        
        item.custom_amount_with_gst = (custom_list_price * qty) * (1 - (custom_margin / 100.0))
        total_without_discount += item.custom_total_buying_price_without_discount
    
    doc.custom_total_without_discount = total_without_discount
    
    # Aggregate custom_amount_with_gst to the header field custom_total_with_gst
    doc.custom_total_with_gst = sum(frappe.utils.flt(item.custom_amount_with_gst) for item in doc.items)
