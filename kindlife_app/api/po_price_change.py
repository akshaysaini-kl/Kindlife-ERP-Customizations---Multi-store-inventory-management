# kindlife_app/api/price_change.py

import frappe
from frappe import _
import json
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import add_days, flt, get_datetime_str, nowdate


@frappe.whitelist()
def get_price_changes(purchase_order_name):
    """
    Get price changes for a purchase order by comparing current prices with PO prices
    """
    try:
        po_doc = frappe.get_doc("Purchase Order", purchase_order_name)
        price_changes = []
        
        # Currency if PO doc
        po_transaction_currency = po_doc.currency
        for item in po_doc.items:
            if not item.item_code or not po_doc.buying_price_list:
                continue
                
            # Get current price from Item Price
            current_price_data = frappe.call(
                "kindlife_app.api.item_price.get_item_price_with_margin",
                item_code=item.item_code,
                price_list=po_doc.buying_price_list,
                supplier=po_doc.supplier,
                transaction_date=po_doc.transaction_date,
                uom=item.uom
            )
            # print("current_price_data",current_price_data)
            

            current_price = 0
            ip_currency = None
            current_price_in_po_currency = 0
            # value of IP of current item and currency of its IP
            if current_price_data and current_price_data.get('price_list_rate'):
                current_price = float(current_price_data.get('price_list_rate', 0))
                ip_currency = current_price_data.get('currency')
                if ip_currency and ip_currency != po_transaction_currency:
                    # Convert current price to PO currency if different
                    exchange_rate = get_exchange_rate(
                        from_currency=ip_currency,
                        to_currency=po_transaction_currency,
                    )
                    current_price_in_po_currency = current_price * exchange_rate

                    pass
                else:
                    # If same currency, no conversion needed
                    current_price_in_po_currency = current_price


            # Price in item table 
            po_price = float(item.price_list_rate or 0)

            # Calculate percentage change
            percentage_change = 0
            if current_price_in_po_currency > 0:
                percentage_change = ((po_price - current_price_in_po_currency) / current_price_in_po_currency) * 100

            # Only include items with price changes
            if abs(percentage_change) > 0.5:  # Consider changes > 0.01%
                price_changes.append({
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'custom_buying_price': item.custom_list_price,
                    'uom': item.uom,
                    'current_price': current_price_in_po_currency,
                    'new_price': po_price,
                    'percentage_change': round(percentage_change, 2),
                    'qty': item.qty,
                    'po_item_name': item.name
                })
        
        return price_changes
        
    except Exception as e:
        # print(e)
        frappe.log_error(f"Error in get_price_changes: {str(e)}")
        return []


@frappe.whitelist()
def create_new_item_prices(purchase_order_name, price_changes_json):
    """
    Create new Item Price records based on price changes
    """
    try:
        po_doc = frappe.get_doc("Purchase Order", purchase_order_name)
        price_changes = json.loads(price_changes_json) if isinstance(price_changes_json, str) else price_changes_json
        
        created_prices = []

        for change in price_changes:
            try:
                # Check if Item Price already exists for this combination
                existing_price = frappe.db.exists("Item Price", {
                    "item_code": change['item_code'],
                    "price_list": po_doc.buying_price_list,
                    "supplier": po_doc.supplier,
                    "uom": change['uom'],
                    "price_list_rate": change['new_price']
                })
                
                if existing_price:
                    continue
                
                # Create new Item Price
                item_price_doc = frappe.new_doc("Item Price")
                item_price_doc.item_code = change['item_code']
                item_price_doc.price_list = po_doc.buying_price_list
                item_price_doc.supplier = po_doc.supplier
                item_price_doc.uom = change['uom']
                item_price_doc.price_list_rate = change['new_price']
                item_price_doc.custom_buying_price = change['custom_buying_price']
                item_price_doc.valid_from = po_doc.transaction_date
                # item_price_doc.workflow_state = "Approved"  # Set as approved as per requirement
                item_price_doc.custom_disable = 0
                item_price_doc.currency = po_doc.currency or "INR"  # Default to INR if no currency set
                
                
                # Set custom buying price if available
                if change.get('custom_buying_price'):
                    item_price_doc.custom_buying_price = change['custom_buying_price']
                
                item_price_doc.insert()
                if item_price_doc.workflow_state == "Draft":
                    item_price_doc.workflow_state = "Pending"
                    item_price_doc.save()
                if item_price_doc.workflow_state == "Pending":
                    item_price_doc.workflow_state = "Approved"
                    item_price_doc.save()
                created_prices.append({
                    'item_code': change['item_code'],
                    'name': item_price_doc.name,
                    'price': change['new_price']
                })
                
            except Exception as item_error:
                frappe.log_error(f"Error creating Item Price for {change['item_code']}: {str(item_error)}")
                continue
        
        return {
            'success': True,
            'created_count': len(created_prices),
            'created_prices': created_prices
        }
        
    except Exception as e:
        frappe.log_error(f"Error in create_new_item_prices: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


@frappe.whitelist()
def check_price_changes_exist(purchase_order_name):
    """
    Check if there are any price changes in the purchase order
    """
    try:
        price_changes = get_price_changes(purchase_order_name)
        return len(price_changes) > 0
    except Exception as e:
        frappe.log_error(f"Error in check_price_changes_exist: {str(e)}")
        return False