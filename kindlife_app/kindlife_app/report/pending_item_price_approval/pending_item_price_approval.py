import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}
    
    columns = get_pending_columns()
    data = get_pending_data(filters)
    
    return columns, data

def get_pending_columns():
    return [
        #  {
        #     "fieldname": "select_row",
        #     "label": "",
        #     "fieldtype": "Data",
        #     "width": 25
        # },
		{
            "label": _("Item Price"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Item Price",
            "width": 100
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 120
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("Price List"),
            "fieldname": "price_list",
            "fieldtype": "Link",
            "options": "Price List",
            "width": 150
        },
        {
            "label": _("MRP(Cur.)"),
            "fieldname": "current_buying_price_formatted",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Buying Price(Cur.)"),
            "fieldname": "current_price_list_rate_formatted",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("MRP(Req.)"),
            "fieldname": "custom_buying_price_formatted",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Buying Price(Req.)"),
            "fieldname": "price_list_rate_formatted",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("Requested By"),
            "fieldname": "custom_requested_by",
            "fieldtype": "Link",
            "options": "User",
            "width": 120
        },
        {
            "label": _("Request Date"),
            "fieldname": "creation",
            "fieldtype": "Datetime",
            "width": 140
        },
        {
            "label": _("Valid From"),
            "fieldname": "valid_from",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": _("Actions"),
            "fieldname": "actions",
            "fieldtype": "Data",
            "width": 150
        }
    ]

def get_pending_data(filters):
	conditions = [ "ip.workflow_state = 'Pending'", "ip.custom_disable = 0"]

	if filters.get('price_list'):
		conditions.append("ip.price_list = %(price_list)s")

	if filters.get('item_code'):
		conditions.append("ip.item_code = %(item_code)s")

	query = f"""
				SELECT 
					ip.name,
					ip.item_code,
					i.item_name,
					ip.price_list,
					ip.price_list_rate,
					ip.custom_buying_price,
					ip.custom_requested_by,
					ip.creation,
					ip.valid_from,
					ip_cur.price_list_rate AS current_price_list_rate,
					ip_cur.custom_buying_price AS current_buying_price,
					ip.currency
				FROM 
					`tabItem Price` ip
				LEFT JOIN 
					`tabItem` i ON ip.item_code = i.name
				
				LEFT JOIN (
					SELECT 
						ip2.item_code,
						ip2.price_list,
						ip2.price_list_rate,
						ip2.custom_buying_price
					FROM 
						`tabItem Price` ip2
					WHERE 
						ip2.workflow_state = 'Approved'
						AND ip2.custom_disable = 0
						AND ip2.valid_from = (
							SELECT MAX(ip3.valid_from)
							FROM `tabItem Price` ip3
							WHERE 
								ip3.item_code = ip2.item_code
								AND ip3.price_list = ip2.price_list
								AND ip3.valid_from <= CURDATE()
								AND ip3.workflow_state = 'Approved'
								AND ip3.custom_disable = 0
						)
						AND ip2.name = (
						SELECT ip4.name
						FROM `tabItem Price` ip4
						WHERE ip4.item_code = ip2.item_code
						AND ip4.price_list = ip2.price_list
						AND ip4.workflow_state = 'Approved'
						AND ip4.valid_from = ip2.valid_from
						AND ip4.custom_disable = 0
						ORDER BY ip4.modified DESC
						LIMIT 1
					)
				) AS ip_cur 
				ON ip_cur.item_code = ip.item_code AND ip_cur.price_list = ip.price_list
				WHERE 
					{' AND '.join(conditions)}
				ORDER BY 
					ip.creation DESC
			"""

	data = frappe.db.sql(query, filters, as_dict=1)

	print("data",data)

	# Format currency values and add action buttons
	for row in data:
		# Format currency values with proper currency symbol
		if row.get('currency'):
			currency_symbol = frappe.db.get_value('Currency', row.get('currency'), 'symbol') or row.get('currency')
			
			# Format current buying price
			if row.get('current_buying_price'):
				row['current_buying_price_formatted'] = f"{frappe.utils.fmt_money(row['current_buying_price'], currency=row.get('currency'))}"
			else:
				row['current_buying_price_formatted'] = f"{currency_symbol} 0.00"
				
			# Format current price list rate
			if row.get('current_price_list_rate'):
				row['current_price_list_rate_formatted'] = f"{frappe.utils.fmt_money(row['current_price_list_rate'], currency=row.get('currency'))}"
			else:
				row['current_price_list_rate_formatted'] = f"{currency_symbol} 0.00"
				
			# Format requested buying price
			if row.get('custom_buying_price'):
				row['custom_buying_price_formatted'] = f"{frappe.utils.fmt_money(row['custom_buying_price'], currency=row.get('currency'))}"
			else:
				row['custom_buying_price_formatted'] = f"{currency_symbol} 0.00"
				
			# Format requested price list rate
			if row.get('price_list_rate'):
				row['price_list_rate_formatted'] = f"{frappe.utils.fmt_money(row['price_list_rate'], currency=row.get('currency'))}"
			else:
				row['price_list_rate_formatted'] = f"{currency_symbol} 0.00"
		else:
			# Fallback if currency is not available
			row['current_buying_price_formatted'] = str(row.get('current_buying_price', 0))
			row['current_price_list_rate_formatted'] = str(row.get('current_price_list_rate', 0))
			row['custom_buying_price_formatted'] = str(row.get('custom_buying_price', 0))
			row['price_list_rate_formatted'] = str(row.get('price_list_rate', 0))

		# Add action buttons
		row['actions'] = f"""
			<button class='btn btn-xs btn-success' 
					onclick='approvePrice("{row.name}")'>
				Approve
			</button>
			<button class='btn btn-xs btn-danger' 
					onclick='rejectPrice("{row.name}")'>
				Reject
			</button>
		"""

	return data