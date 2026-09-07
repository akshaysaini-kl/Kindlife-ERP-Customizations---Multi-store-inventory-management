import frappe
from frappe import _
from erpnext.stock.get_item_details import get_item_price

@frappe.whitelist()
def create_item_price_for_approval(item_code, price_list, new_buying_price, new_mrp, valid_from, custom_discount_on=None, custom_discount_percentage=0, custom_discount_amount=0):
    try:
        # Create new Item Price document
        item_price = frappe.new_doc('Item Price')
        item_price.item_code = item_code
        item_price.price_list = price_list
        item_price.custom_buying_price = new_mrp
        item_price.price_list_rate = new_buying_price
        item_price.valid_from = valid_from
        
        if custom_discount_on:
            item_price.custom_discount_on = custom_discount_on
        
        if custom_discount_percentage:
            item_price.custom_discount_percentage = custom_discount_percentage

        if custom_discount_amount:
            item_price.custom_discount_amount = custom_discount_amount
        # item_price.workflow_state = 'Pending Approval'
        
        # Set custom fields if needed
        # item_price.requested_by = frappe.session.user
        # item_price.request_date = frappe.utils.now()
        
        item_price.insert()
        print("p1")
        if item_price.workflow_state == "Draft":
            item_price.workflow_state="Pending"
            item_price.save()   
        
        # Send notification to Purchase Manager
        # send_approval_notification(item_price.name)
        
        return item_price.name
        
    except Exception as e:
        frappe.throw(_('Error creating item price: {0}').format(str(e)))

def send_approval_notification(item_price_name):
    """Send notification to Purchase Manager for approval"""
    
    # Get Purchase Managers
    purchase_managers = frappe.get_all('Has Role', 
        filters={'role': 'Purchase Manager'}, 
        fields=['parent']
    )
    
    recipients = [pm.parent for pm in purchase_managers]
    
    if recipients:
        frappe.sendmail(
            recipients=recipients,
            subject=_('New Item Price Approval Required'),
            message=_('A new item price change request requires your approval. Document: {0}').format(item_price_name),
            reference_doctype='Item Price',
            reference_name=item_price_name
        )


@frappe.whitelist()
def bulk_approve_prices(item_price_names):
    """Bulk approve multiple item prices"""
    try:
        if isinstance(item_price_names, str):
            import json
            item_price_names = json.loads(item_price_names)
        
        approved_count = 0
        failed_items = []
        
        for name in item_price_names:
            try:
                doc = frappe.get_doc('Item Price', name)
                if doc.workflow_state == 'Pending':
                    doc.workflow_state = 'Approved'
                    doc.custom_approved_by = frappe.session.user
                    doc.custom_approved_at = frappe.utils.today()
                    doc.save()
                    approved_count += 1
            except Exception as e:
                failed_items.append(f"{name}: {str(e)}")
        
        result = {
            'success': True,
            'approved_count': approved_count,
            'failed_items': failed_items,
            'message': f'Successfully approved {approved_count} item price(s)'
        }
        
        if failed_items:
            result['message'] += f'. Failed: {len(failed_items)} item(s)'
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Bulk approval failed: {str(e)}'
        }

@frappe.whitelist()
def bulk_reject_prices(item_price_names):
    """Bulk reject multiple item prices"""
    try:
        if isinstance(item_price_names, str):
            import json
            item_price_names = json.loads(item_price_names)
        
        rejected_count = 0
        failed_items = []
        
        for name in item_price_names:
            try:
                doc = frappe.get_doc('Item Price', name)
                if doc.workflow_state == 'Pending':
                    doc.workflow_state = 'Rejected'
                    doc.custom_approved_by = frappe.session.user
                    doc.custom_approved_at = frappe.utils.today()
                    doc.save()
                    rejected_count += 1
            except Exception as e:
                failed_items.append(f"{name}: {str(e)}")
        
        result = {
            'success': True,
            'rejected_count': rejected_count,
            'failed_items': failed_items,
            'message': f'Successfully rejected {rejected_count} item price(s)'
        }
        
        if failed_items:
            result['message'] += f'. Failed: {len(failed_items)} item(s)'
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Bulk rejection failed: {str(e)}'
        }
    

@frappe.whitelist()
def get_item_price_history(item_code, price_list=None):
    """Get item price history for display in HTML field"""
    
    try:
        # Base query
        conditions = [
            "ip.item_code = %(item_code)s",
            "ip.workflow_state IN ('Approved', 'Rejected')"
        ]
        values = {"item_code": item_code}
        
        # Add price list filter if provided
        if price_list:
            conditions.append("ip.price_list = %(price_list)s")
            values["price_list"] = price_list
        
        # Build the query
        query = f"""
            SELECT 
                ip.name,
                ip.item_code,
                i.item_name,
                ip.price_list,
                ip.price_list_rate,
                ip.custom_buying_price,
                ip.valid_from,
                ip.valid_upto,
                ip.owner as requested_by,
                ip.workflow_state,
                ip.custom_approved_by,
                ip.custom_approved_at,
                ip.creation,
                ip.modified,
                ip.modified_by,
                ip.currency
            FROM 
                `tabItem Price` ip
            LEFT JOIN 
                `tabItem` i ON ip.item_code = i.name
            WHERE
                {' AND '.join(conditions)}
            ORDER BY 
                ip.creation DESC
            LIMIT 50
        """
        
        data = frappe.db.sql(query, values, as_dict=True)
        # print("data",data)
        
        # Process the data to add additional information
        processed_data = []
        for row in data:
            # Format the data
            processed_row = {
                "name": row.get("name"),
                "item_code": row.get("item_code"),
                "item_name": row.get("item_name") or row.get("item_code"),
                "price_list": row.get("price_list"),
                "price_list_rate": row.get("price_list_rate"),
                "custom_buying_price": row.get("custom_buying_price"),
                "valid_from": row.get("valid_from"),
                "valid_upto": row.get("valid_upto"),
                "requested_by": get_user_fullname(row.get("requested_by")) or row.get("requested_by"),
                "approval_status": row.get("workflow_state") or "Pending",
                "approved_by": get_user_fullname(row.get("custom_approved_by")) if row.get("custom_approved_by") else None,
                "approved_date": row.get("approved_date"),
                "rejected_by": get_user_fullname(row.get("rejected_by")) if row.get("rejected_by") else None,
                "rejection_date": row.get("rejection_date"),
                "creation": row.get("creation"),
                "modified": row.get("modified"),
                "modified_by": get_user_fullname(row.get("modified_by")) or row.get("modified_by"),
                "owner": get_user_fullname(row.get("requested_by")) or row.get("requested_by"),
                "currency": row.get("currency") 
            }
            
            processed_data.append(processed_row)
        
        return processed_data
        
    except Exception as e:
        print(str(e))
        frappe.log_error(f"Error getting item price history: {str(e)}")
        return []

def get_user_fullname(email):
    """Get user's full name from email"""
    if not email:
        return None
    
    try:
        user = frappe.get_doc("User", email)
        return user.full_name or user.first_name or email
    except:
        return email


@frappe.whitelist()
def get_item_price_for_purchase_order(item_code, price_list, supplier=None, transaction_date=None, uom=None):
    """
    Get item price details for purchase order using the overridden get_item_price function
    """
    try:
        if not item_code or not price_list:
            return None
            
        # Prepare arguments for get_item_price function
        args = frappe._dict({
            'price_list': price_list,
            'uom': uom or frappe.db.get_value('Item', item_code, 'stock_uom'),
            'transaction_date': transaction_date or frappe.utils.today(),
            'supplier': supplier
        })
        
        # Call the overridden get_item_price function
        price_data = get_item_price(args, item_code, ignore_party=True)
        # print("price_data",price_data)
        
        if price_data:
            # Return the first matching price record
            price_record = price_data[0]
            return {
                'name': price_record[0],
                'price_list_rate': price_record[1],
                'uom': price_record[2],
                'custom_buying_price': price_record[3] if len(price_record) > 3 else None
            }
        else:
            return None
            
    except Exception as e:
        # print(e)
        frappe.log_error(f"Error in get_item_price_for_purchase_order: {str(e)}")
        return None


@frappe.whitelist()
def get_item_price_for_sales_order(item_code, price_list, customer=None, transaction_date=None, uom=None):
    """
    Get item price details for sales order using the overridden get_item_price function
    """
    try:
        if not item_code or not price_list:
            return None
            
        # Prepare arguments for get_item_price function
        args = frappe._dict({
            'price_list': price_list,
            'uom': uom or frappe.db.get_value('Item', item_code, 'stock_uom'),
            'transaction_date': transaction_date or frappe.utils.today(),
            'customer': customer
        })
        
        # Call the overridden get_item_price function
        price_data = get_item_price(args, item_code, ignore_party=True)
        
        if price_data:
            # Return the first matching price record
            price_record = price_data[0]
            return {
                'name': price_record[0],
                'price_list_rate': price_record[1],
                'uom': price_record[2],
                'custom_buying_price': price_record[3] if len(price_record) > 3 else None
            }
        else:
            return None
            
    except Exception as e:
        frappe.log_error(f"Error in get_item_price_for_sales_order: {str(e)}")
        return None


@frappe.whitelist()
def get_item_price_with_margin(item_code, price_list, supplier=None, transaction_date=None, uom=None):
    """
    Get item price details including margin calculation
    """
    try:
        # Get price data using the API above
        price_data = get_item_price_for_purchase_order(item_code, price_list, supplier, transaction_date, uom)
        
        if not price_data:
            return None

        # Get additional data from Item Price doctype for margin calculation
        item_price_doc = frappe.get_doc('Item Price', price_data['name'])
        
        result = {
            'price_list_rate': price_data['price_list_rate'],
            'custom_buying_price': price_data['custom_buying_price'],
            'uom': price_data['uom'],
            'custom_margin': getattr(item_price_doc, 'custom_margin', None),
            'currency': getattr(item_price_doc, 'currency', None)
        }
        
        return result
        
    except Exception as e:
        # print("--",e)
        frappe.log_error(f"Error in get_item_price_with_margin: {str(e)}")
        return None

@frappe.whitelist()
def get_item_price_with_margin_for_sales(item_code, price_list, customer=None, transaction_date=None, uom=None):
    """
    Get item price details including margin calculation for sales transactions
    """
    try:
        # Get price data using the sales API above
        price_data = get_item_price_for_sales_order(item_code, price_list, customer, transaction_date, uom)
        
        if not price_data:
            return None
            
        # Get additional data from Item Price doctype for margin calculation
        item_price_doc = frappe.get_doc('Item Price', price_data['name'])
        
        result = {
            'price_list_rate': price_data['price_list_rate'],
            'custom_buying_price': price_data['custom_buying_price'],
            'uom': price_data['uom'],
            'custom_margin': getattr(item_price_doc, 'custom_margin', None),
            'currency': getattr(item_price_doc, 'currency', None)
        }
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in get_item_price_with_margin_for_sales: {str(e)}")
        return None