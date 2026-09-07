# Copyright (c) 2025, Auriga IT and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class ConsolidatedPickList(Document):
	def validate(self):
		"""Validate the consolidated pick list"""
		if not self.items:
			frappe.throw(_("Please add items to the Consolidated Pick List"))
	
	def before_save(self):
		"""Update Pick List references when saving"""
		if not self.is_new():
			return
			
		# Get all pick lists referenced in items
		pick_lists = set()
		for item in self.items:
			if item.pick_lists:
				for pl in item.pick_lists.split('\n'):
					if pl.strip():
						pick_lists.add(pl.strip())
		
		print("pick_lists",pick_lists)
		# Update Pick List with CPL reference and status
		for pick_list in pick_lists:
			frappe.db.set_value('Pick List', pick_list, {
				'custom_consolidate_pick_list': self.name,
				'custom_cpl_status': 'CPL Created'
			})
			# frappe.db.commit()

	def on_submit(self):
		"""Update Pick List status to Items Picked on submit"""
		# Get all pick lists referenced in items
		pick_lists = set()
		for item in self.items:
			if item.pick_lists:
				for pl in item.pick_lists.split('\n'):
					if pl.strip():
						pick_lists.add(pl.strip())
		
		# Update Pick List status to Items Picked
		for pick_list in pick_lists:
			frappe.db.set_value('Pick List', pick_list, 'custom_cpl_status', 'Items Picked')
	
	def on_cancel(self):
		"""Clear Pick List references on cancel"""
		self.clear_pick_list_references()
	
	def on_trash(self):
		"""Clear Pick List references on delete"""
		self.clear_pick_list_references()
	
	def clear_pick_list_references(self):
		"""Helper method to clear Pick List references"""
		# Get all pick lists referenced in items
		pick_lists = set()
		for item in self.items:
			if item.pick_lists:
				for pl in item.pick_lists.split('\n'):
					if pl.strip():
						pick_lists.add(pl.strip())
		
		# Clear Pick List references
		for pick_list in pick_lists:
			frappe.db.set_value('Pick List', pick_list, {
				'custom_consolidate_pick_list': None,
				'custom_cpl_status': None
			})
		frappe.db.commit()


@frappe.whitelist()
def get_pick_lists_for_consolidation(company=None):
	"""
	Get Pick Lists that are not yet consolidated
	Returns list of Pick Lists with their details
	"""
	filters = {
		'docstatus': 1,
		'status': ['in', ['Open', 'Partly Delivered']],
		'custom_consolidate_pick_list': ['is', 'not set']
	}
	
	if company:
		filters['company'] = company
	
	# Get pick lists
	pick_lists = frappe.get_all(
		'Pick List',
		filters=filters,
		fields=['name', 'company', 'creation'],
		order_by='creation desc'
	)
	
	# Add additional details
	result = []
	for pl in pick_lists:
		# Get sales orders from pick list items
		sales_orders = frappe.db.sql("""
			SELECT DISTINCT sales_order
			FROM `tabPick List Item`
			WHERE parent = %s AND sales_order IS NOT NULL
		""", pl.name, as_dict=True)
		
		sales_order_list = ', '.join([so.sales_order for so in sales_orders if so.sales_order])
		
		# Get total items count
		total_items = frappe.db.count('Pick List Item', {'parent': pl.name})
		
		# Get CPL Status
		cpl_status = frappe.db.get_value('Pick List', pl.name, 'custom_cpl_status') or ''
		
		result.append({
			'name': pl.name,
			'sales_order': sales_order_list,
			'total_items': total_items,
			'cpl_status': cpl_status,
			'company': pl.company
		})
	
	return result


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_pick_list_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Custom query for Pick List MultiSelectDialog using frappe.get_list() for permission-aware filtering
	Returns Pick Lists with Sales Order information from first Pick List Item
	"""
	# Build filters for frappe.get_list()
	get_list_filters = {}
	
	if filters:
		# Handle docstatus filter
		if 'docstatus' in filters:
			get_list_filters['docstatus'] = filters.get('docstatus')
		
		# Handle status filter
		if filters.get('status'):
			status_list = filters.get('status')
			if isinstance(status_list, list) and len(status_list) > 1:
				# Handle ['in', ['Open', 'Partly Delivered']]
				status_values = status_list[1] if status_list[0] == 'in' else status_list
				get_list_filters['status'] = ['in', status_values]
			else:
				get_list_filters['status'] = status_list
		
		# Handle custom_consolidate_pick_list filter (not set)
		if filters.get('custom_consolidate_pick_list'):
			get_list_filters['custom_consolidate_pick_list'] = ['is', 'not set']
		
		# Handle custom_type filter
		if filters.get('custom_type'):
			get_list_filters['custom_type'] = filters.get('custom_type')
		
		# Handle parent_warehouse filter
		if filters.get('parent_warehouse'):
			get_list_filters['parent_warehouse'] = filters.get('parent_warehouse')
		
		# Handle company filter
		if filters.get('company'):
			get_list_filters['company'] = filters.get('company')
	
	# Handle text search - search in Pick List name
	if txt:
		get_list_filters['name'] = ['like', f'%{txt}%']
	
	# Get Pick Lists using frappe.get_list() (permission-aware)
	pick_lists = frappe.get_list(
		"Pick List",
		filters=get_list_filters,
		fields=["name", "company", "status", "creation"],
		order_by="creation desc",
		start=start,
		page_length=page_len
	)
	
	if not pick_lists:
		return []
	
	# Get Pick List names for sales order lookup
	pl_names = [pl.name for pl in pick_lists]
	
	# Get first sales order for each Pick List using Query Builder
	from frappe.query_builder import DocType
	
	pli = DocType("Pick List Item")
	sales_order_data = (
		frappe.qb.from_(pli)
		.select(pli.parent, pli.sales_order)
		.where(pli.parent.isin(pl_names))
		.where(pli.sales_order.isnotnull())
		.orderby(pli.parent, pli.idx)
	).run(as_dict=True)
	
	# Create mapping of pick list to first sales order
	pl_to_so = {}
	for item in sales_order_data:
		if item.parent not in pl_to_so:  # Only take first sales order
			pl_to_so[item.parent] = item.sales_order
	
	# If txt search includes sales order search, filter by sales order
	if txt:
		# Get Pick Lists that have sales orders matching the text
		matching_sales_orders = [
			item.parent for item in sales_order_data 
			if txt.lower() in (item.sales_order or '').lower()
		]
		
		# Filter pick_lists to include only those with matching names or sales orders
		pick_lists = [
			pl for pl in pick_lists 
			if txt.lower() in pl.name.lower() or pl.name in matching_sales_orders
		]
	
	# Build final result with sales order information
	result = []
	for pl in pick_lists:
		result.append({
			'name': pl.name,
			'company': pl.company,
			'sales_order': pl_to_so.get(pl.name, ''),
			'status': pl.status
		})
	
	return result


@frappe.whitelist()
def get_items_from_pick_lists(source_name, target_doc=None, source_parent=None):
	"""
	Get consolidated items from selected Pick Lists
	Groups items by item_code, warehouse, and batch
	This method is called by the standard MultiSelectDialog via frappe.model.mapper
	
	Args:
		source_name: List of Pick List names (can be string or list)
		target_doc: Target Consolidated Pick List document
		source_parent: Parent document (not used, but required by mapper)
	"""
	import json
	
	# Parse source_name - it can be a list, a JSON string, or a single value
	if isinstance(source_name, str):
		# Try to parse as JSON, if it fails treat it as a single value
		try:
			if source_name.strip():
				source_names = json.loads(source_name)
			else:
				source_names = []
		except (json.JSONDecodeError, ValueError):
			# Single Pick List name
			source_names = [source_name]
	elif isinstance(source_name, list):
		source_names = source_name
	else:
		# Single value
		source_names = [source_name] if source_name else []
	
	if not source_names:
		frappe.throw(_("Please select at least one Pick List"))
	
	# Parse target_doc if needed
	if isinstance(target_doc, str):
		target_doc = json.loads(target_doc)
	
	# Create or get target document
	if target_doc:
		target_doc = frappe.get_doc(target_doc)
	else:
		target_doc = frappe.new_doc("Consolidated Pick List")
	
	# Set date
	target_doc.date = today()
	
	print("source_names",source_names)
	# Get all pick list items
	items_data = frappe.db.sql("""
		SELECT 
			pli.item_code,
			pli.warehouse,
			pli.batch_no,
			SUM(pli.qty) as total_qty,
			pli.parent as pick_list
		FROM `tabPick List Item` pli
		WHERE pli.parent IN ({})
		GROUP BY pli.item_code, pli.warehouse, pli.batch_no, pli.parent
		ORDER BY pli.item_code, pli.warehouse, pli.batch_no
	""".format(','.join(['%s'] * len(source_names))), tuple(source_names), as_dict=True)
	
	# Group items by item, warehouse, and batch
	consolidated_items = {}
	for item in items_data:
		key = (item.item_code, item.warehouse, item.batch_no or '')
		
		if key not in consolidated_items:
			consolidated_items[key] = {
				'item': item.item_code,
				'warehouse': item.warehouse,
				'batch': item.batch_no,
				'qty': 0,
				'pick_lists': []
			}
		
		consolidated_items[key]['qty'] += flt(item.total_qty)
		if item.pick_list not in consolidated_items[key]['pick_lists']:
			consolidated_items[key]['pick_lists'].append(item.pick_list)
	
	# Clear existing items in target
	target_doc.items = []
	
	# Add consolidated items
	for item_data in consolidated_items.values():
		target_doc.append('items', {
			'item': item_data['item'],
			'warehouse': item_data['warehouse'],
			'batch': item_data['batch'],
			'qty': item_data['qty'],
			'pick_lists': '\n'.join(item_data['pick_lists'])
		})
	
	return target_doc


@frappe.whitelist()
def create_cpl_from_pick_lists(pick_list_names, type=None, warehouse=None):
	"""
	Create a Consolidated Pick List from selected Pick Lists (called from list view).
	Validates pick lists, consolidates items, and returns the new CPL name.
	"""
	import json

	if isinstance(pick_list_names, str):
		pick_list_names = json.loads(pick_list_names)

	if not pick_list_names:
		frappe.throw(_("Please select at least one Pick List"))

	# Validate all pick lists (must be draft - scanning happens in draft mode)
	for pl_name in pick_list_names:
		pl = frappe.get_doc("Pick List", pl_name)
		if pl.docstatus != 0:
			frappe.throw(_("Pick List {0} is not in draft mode").format(pl_name))
		if pl.custom_consolidate_pick_list:
			frappe.throw(
				_("Pick List {0} is already linked to CPL {1}").format(
					pl_name, pl.custom_consolidate_pick_list
				)
			)

	# Use existing consolidation logic
	cpl_doc = get_items_from_pick_lists(
		source_name=json.dumps(pick_list_names),
		target_doc=None
	)

	# Set type and warehouse from the dialog
	if type:
		cpl_doc.type = type
	if warehouse:
		cpl_doc.warehouse = warehouse

	# Set company from the first pick list
	first_pl = frappe.get_doc("Pick List", pick_list_names[0])
	cpl_doc.company = first_pl.company

	cpl_doc.insert()

	return cpl_doc.name


@frappe.whitelist()
def get_pick_list_details(cpl_name):
	"""
	Get detailed information about all Pick Lists linked to a CPL.
	Returns pick list info with their items for the collapsible HTML table.
	"""
	cpl_doc = frappe.get_doc("Consolidated Pick List", cpl_name)

	# Extract all unique pick list names from CPL items
	pick_list_names = set()
	for item in cpl_doc.items:
		if item.pick_lists:
			for pl in item.pick_lists.split('\n'):
				if pl.strip():
					pick_list_names.add(pl.strip())

	if not pick_list_names:
		return []

	pl_names_list = list(pick_list_names)

	# Fetch pick list header info in bulk
	pick_lists = frappe.get_all(
		"Pick List",
		filters={"name": ["in", pl_names_list]},
		fields=[
			"name", "status", "customer", "customer_name",
			"custom_scanning_percent", "custom_cpl_status",
			"custom_type", "parent_warehouse"
		]
	)

	# Fetch all pick list items in bulk
	items_data = frappe.db.sql("""
		SELECT
			pli.parent as pick_list,
			pli.item_code,
			pli.item_name,
			pli.batch_no,
			pli.warehouse,
			pli.qty,
			pli.picked_qty
		FROM `tabPick List Item` pli
		WHERE pli.parent IN ({})
		ORDER BY pli.parent, pli.idx
	""".format(','.join(['%s'] * len(pl_names_list))), tuple(pl_names_list), as_dict=True)

	# Group items by pick list
	items_by_pl = {}
	for item in items_data:
		items_by_pl.setdefault(item.pick_list, []).append(item)

	# Build result
	result = []
	for pl in pick_lists:
		result.append({
			"name": pl.name,
			"status": pl.status,
			"customer": pl.customer,
			"customer_name": pl.customer_name,
			"scanning_percent": flt(pl.custom_scanning_percent, 1),
			"cpl_status": pl.custom_cpl_status or "",
			"type": pl.custom_type or "",
			"warehouse": pl.parent_warehouse or "",
			"items": items_by_pl.get(pl.name, [])
		})

	# Sort by name for consistency
	result.sort(key=lambda x: x["name"])

	return result


