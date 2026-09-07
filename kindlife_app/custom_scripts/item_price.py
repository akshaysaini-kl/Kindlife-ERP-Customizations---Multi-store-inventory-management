import frappe
from frappe.utils import now, flt
from erpnext.setup.utils import get_exchange_rate


def item_price_validate(doc,method):
    # Set conversion rate and price list rate in company currency
    set_conversion_rate_and_company_currency_rate(doc)
    
    # set_item_price_fields-------------------------
    calculate_custom_discount(doc)
    
    if doc.custom_buying_price and doc.custom_price_list_ratecompany_currency:
        doc.custom_margin =(float(doc.custom_buying_price) - float(doc.custom_price_list_ratecompany_currency))/float(doc.custom_buying_price)*100

    # Set approved_by and requested_by based on workflow state
    if not doc.custom_approved_by and doc.workflow_state == "Approved":
        doc.custom_approved_by = frappe.session.user
        doc.custom_approved_at = now()
        # print("doc.custom_approved_by", doc.custom_approved_by, "doc.custom_approved_at", doc.custom_approved_at)

    if not doc.custom_requested_by:
        doc.custom_requested_by = frappe.session.user
        # print("doc.custom_requested_by", doc.custom_requested_by)




    # fill_supplie_field-----------------------------
    if not doc.price_list:
        return

    flags = frappe.db.get_value(
        "Price List",
        doc.price_list,
        ["buying", "selling"],
        as_dict=True
    )


    if flags.get("buying"):
        supplier_name = frappe.get_value(
            "Supplier",
            {"default_price_list": doc.price_list},
            "name"
        )

        doc.supplier = supplier_name or None






# This makes sure that the workflow state is set to Approved when the document is created or updated by a Purchase Manager
def set_wokflow_state(doc, method):
    doc.workflow_state = 'Draft'
    if doc.workflow_state == 'Draft' and "Purchase Manager" in frappe.get_roles(frappe.session.user):
        doc.workflow_state = 'Pending'
        doc.save(ignore_permissions=True)
    if doc.workflow_state == 'Pending' and "Purchase Manager" in frappe.get_roles(frappe.session.user):
        doc.workflow_state = 'Approved'
        doc.save(ignore_permissions=True)


def set_conversion_rate_and_company_currency_rate(doc):
    """
    Set custom_conversion_rate and custom_price_list_ratecompany_currency
    based on the selected currency field.
    
    - custom_conversion_rate: Exchange rate from selected currency to company currency (INR)
    - custom_price_list_ratecompany_currency: price_list_rate converted to company currency (INR)
    
    Similar to how conversion_rate is handled in Purchase Order
    """
    # Get company currency (default to INR as mentioned in requirements)
    company_currency = frappe.db.get_default("currency") or "INR"
    
    # Get the currency from the Item Price document
    item_price_currency = doc.currency or company_currency
    
    # If currency is same as company currency, conversion rate is 1
    if item_price_currency == company_currency:
        doc.custom_conversion_rate = 1.0
        doc.custom_price_list_ratecompany_currency = flt(doc.price_list_rate)
    else:
        # Get exchange rate from item price currency to company currency
        try:
            exchange_rate = get_exchange_rate(
                from_currency=item_price_currency,
                to_currency=company_currency,
                transaction_date=doc.valid_from or frappe.utils.nowdate()
            )
            doc.custom_conversion_rate = flt(exchange_rate)
            
            # Convert price_list_rate to company currency
            # price in company currency = price in foreign currency * exchange rate
            doc.custom_price_list_ratecompany_currency = flt(doc.price_list_rate) * flt(exchange_rate)
        except Exception as e:
            frappe.log_error(f"Error getting exchange rate for {item_price_currency} to {company_currency}: {str(e)}")
            # Set default values if exchange rate fetch fails
            doc.custom_conversion_rate = 1.0
            doc.custom_price_list_ratecompany_currency = flt(doc.price_list_rate)


def calculate_custom_discount(doc):
    """
    Calculate discount based on custom_discount_on field (MRP or Selling Price).
    price_list_rate is intentionally NOT modified — discount applies on MRP/Selling
    Price only to compute custom_discount_amount.
    """
    custom_discount_on = doc.get('custom_discount_on')
    discount_percentage = flt(doc.get('custom_discount_percentage'))

    if not discount_percentage:
        return

    if custom_discount_on == 'MRP':
        custom_buying_price = flt(doc.get('custom_buying_price'))
        if custom_buying_price > 0:
            discount_amount = flt(custom_buying_price * (discount_percentage / 100.0), doc.precision('custom_discount_amount'))
            doc.custom_discount_amount = discount_amount
            # price_list_rate is intentionally NOT updated

    elif custom_discount_on == 'Selling Price':
        price_list_rate = flt(doc.price_list_rate)
        if price_list_rate > 0:
            discount_amount = flt(price_list_rate * (discount_percentage / 100.0), doc.precision('custom_discount_amount'))
            doc.custom_discount_amount = discount_amount
            # price_list_rate is intentionally NOT updated
