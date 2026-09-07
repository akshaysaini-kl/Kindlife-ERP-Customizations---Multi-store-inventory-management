import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}
    
    # Validate mandatory filter
    if not filters.get('price_list'):
        frappe.throw(_('Price List is mandatory'))
    
    columns = get_columns(filters)
    data = get_data(filters)
    
    return columns, data

def get_columns(filters):
    # Get the currency from the selected price list
    
    return [
        {
            "label": _("Inventory ID"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 120
        },
        {
            "label": _("UOM"),
            "fieldname": "uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 80
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("MRP"),
            "fieldname": "custom_buying_price_formatted",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Discount On"),
            "fieldname": "custom_discount_on",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Discount %"),
            "fieldname": "custom_discount_percentage",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Discount Amount"),
            "fieldname": "custom_discount_amount",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Buying Price"),
            "fieldname": "price_list_rate_formatted",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Approved By"),
            "fieldname": "custom_approved_by",
            "fieldtype": "Link",
            "options": "User",
            "width": 120
        },
        {
            "label": _("Approved Date"),
            "fieldname": "custom_approved_at",
            "fieldtype": "Date",
            "width": 130
        },
        {
            "label": _("Valid From"),
            "fieldname": "valid_from",
            "fieldtype": "Date",
            "width": 130
        },
        # {
        #     "label": _("Pending Approvals"),
        #     "fieldname": "pending_count",
        #     "fieldtype": "Int",
        #     "width": 120
        # },
        {
            "label": _("Actions"),
            "fieldname": "actions",
            "fieldtype": "Data",
            "width": 150
        }
    ]

def get_data(filters):
    price_list = filters.get('price_list')
        
    # Get current valid item prices
    query = """
        SELECT 
			ip.item_code,
			i.stock_uom as uom,
			i.item_name,
			ip.price_list_rate,
			ip.custom_buying_price,
            ip.custom_discount_on,
            ip.custom_discount_percentage,
            ip.custom_discount_amount,
			ip.custom_approved_by,
			ip.custom_approved_at,
			ip.valid_from,
			ip.name as item_price_name,
			ip.currency,
			CURDATE() as curdate
		FROM 
			`tabItem Price` ip
		LEFT JOIN 
			`tabItem` i ON ip.item_code = i.name
		
		WHERE 
			ip.price_list = %(price_list)s
            AND ip.custom_disable = 0
			AND ip.workflow_state='Approved'
			AND ip.valid_from = (
				SELECT MAX(ip2.valid_from)
				FROM `tabItem Price` ip2
				WHERE ip2.item_code = ip.item_code
				AND ip2.price_list = ip.price_list
				AND ip2.valid_from <= CURDATE()
				AND ip2.workflow_state='Approved'
                AND ip2.custom_disable = 0
			)
			AND ip.name = (
				SELECT ip3.name
				FROM `tabItem Price` ip3
				WHERE ip3.item_code = ip.item_code
				AND ip3.price_list = ip.price_list
				AND ip3.workflow_state = 'Approved'
				AND ip3.valid_from = ip.valid_from
                AND ip3.custom_disable = 0
				ORDER BY ip3.modified DESC
				LIMIT 1
			)
		ORDER BY 
			ip.item_code
    """
    
    data = frappe.db.sql(query, {'price_list': price_list}, as_dict=1)
    print("data",data)
    
    # Add pending approval count for each item
    for row in data:
        # Format currency values with proper currency symbol
        if row.get('currency'):
            currency_symbol = frappe.db.get_value('Currency', row.get('currency'), 'symbol') or row.get('currency')
            
            # Format the currency values
            if row.get('custom_buying_price'):
                row['custom_buying_price_formatted'] = f"{frappe.utils.fmt_money(row['custom_buying_price'], currency=row.get('currency'))}"
            else:
                row['custom_buying_price_formatted'] = f"{currency_symbol} 0.00"
                
            if row.get('price_list_rate'):
                row['price_list_rate_formatted'] = f"{frappe.utils.fmt_money(row['price_list_rate'], currency=row.get('currency'))}"
            else:
                row['price_list_rate_formatted'] = f"{currency_symbol} 0.00"
        else:
            # Fallback if currency is not available
            row['custom_buying_price_formatted'] = str(row.get('custom_buying_price', 0))
            row['price_list_rate_formatted'] = str(row.get('price_list_rate', 0))
        
        pending_count = frappe.db.count('Item Price', {
            'item_code': row.item_code,
            'price_list': price_list,
            'docstatus': 0,
            'workflow_state': 'Pending'
        })
        row['pending_count'] = pending_count
        
        # Add action buttons HTML
        # Add combined actions HTML with pending count and change price button
        pending_badge = ""
        if row['pending_count'] > 0:
            pending_badge = f"""
                <span class="badge badge-warning" 
                     style="cursor: pointer; font-size: 10px; padding: 3px 6px; border-radius: 10px; margin-right: 5px;"
                     onclick="viewPendingPrices('{row.item_code}', '{price_list}')"
                     title="Click to view {row['pending_count']} pending approval(s)">
                    <i class="fa fa-clock-o" style="font-size: 9px;"></i> {row['pending_count']}
                </span>
            """
        else:
            pending_badge = f"""
                <span class="badge badge-success" 
                      style="font-size: 10px; padding: 3px 6px; border-radius: 10px; margin-right: 5px;">
                    <i class="fa fa-check" style="font-size: 9px;"></i> 0
                </span>
            """
        
        row['actions'] = f"""
            <div style="display: flex; align-items: center; justify-content: center; gap: 5px;">
                {pending_badge}
                <button class='btn btn-xs btn-primary' 
                        style='padding: 2px 6px; font-size: 10px; min-width: auto;'
                        onclick='changePrice("{row.item_code}", "{price_list}")'
                        title='Change Price'>
                    <i class="fa fa-edit"></i>
                </button>
            </div>
        """
    
    return data