# sales_order_api.py
# API endpoint for CS Cart to create Sales Orders in ERPNext

import frappe
from frappe import _
from frappe.utils import nowdate, flt
import json
import base64
from kindlife_app.utils.shipment_utils import sync_shipment_docs_for_so
from kindlife_app.services.cscart_service import CS_CART_CONSTANTS

@frappe.whitelist()
def create_sales_order(data):
    """
    API endpoint to create Sales Order from CS Cart
    
    Expected JSON structure:
    {
        "order_id": "CS-12345",
        "order_date": "2025-10-03",
        "delivery_address": {
            "address_line1": "123 Main Street",
            "address_line2": "Apartment 4B",
            "city": "Jaipur",
            "state": "Rajasthan",
            "pincode": "302001",
            "country": "India",
            "phone": "+91-9876543210",
            "email": "customer@example.com",
            "contact_person": "John Doe"
        },
        "items": [
            {
                "item_code": "ITM-001",
                "qty": 2,
                "warehouse": "WH-A-01",
            },
            {
                "item_code": "ITM-002",
                "qty": 1,
                "warehouse": "WH-A-02",
            }
        ],
    }
    """
    
    try:
        # Parse data if it's a string
        if isinstance(data, str):
            data = json.loads(data)
        
        # Validate required fields
        validate_data(data)

        # Check if Sales Order already exists
        order_id = data.get("order_id")
        existing_so_name = frappe.db.get_value("Sales Order", {"po_no": order_id, "docstatus": ["<", 2]}, "name")
        
        if existing_so_name:
            existing_so = frappe.get_doc("Sales Order", existing_so_name)
            
            # Compare items to check for updates
            incoming_items = {}
            for item in data.get("items", []):
                item_code = item.get("item_code")
                incoming_items[item_code] = incoming_items.get(item_code, 0) + flt(item.get("qty"))
            
            existing_items_dict = {}
            for item in existing_so.items:
                existing_items_dict[item.item_code] = existing_items_dict.get(item.item_code, 0) + flt(item.qty)
            
            items_updated = False
            # Check if items are different
            if len(incoming_items) != len(existing_items_dict):
                items_updated = True
            else:
                for item_code, qty in incoming_items.items():
                    if item_code not in existing_items_dict or existing_items_dict[item_code] != qty:
                        items_updated = True
                        break
            
            message = "Order already exists"
            
            if items_updated:
                # Use db.set_value to safely update the flag even if SO is submitted
                frappe.db.set_value("Sales Order", existing_so.name, "custom_items_updated_on_cs_cart", 1)
                frappe.db.commit()
                message = "Order already exists and items updated on CS Cart"
                
            return {
                "status": "success",
                "message": message,
                "sales_order": existing_so.name,
                "sales_order_id": existing_so.name,
                "order_total": existing_so.grand_total,
                "items_updated": items_updated
            }
        
        # Create or get delivery address
        shipping_address = get_address("Customer",CS_CART_CONSTANTS.get("CUSTOMER_NAME"))
        
        # Extract shipping address details from data
        delivery_address = data.get("delivery_address", {})
        shipping_address_line1 = delivery_address.get("address_line1", "")
        shipping_address_line2 = delivery_address.get("address_line2", "")
        shipping_city = delivery_address.get("city")
        shipping_state = delivery_address.get("state")
        shipping_pincode = delivery_address.get("pincode")
        
        # Create Sales Order
        sales_order = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": CS_CART_CONSTANTS.get("CUSTOMER_NAME"),  # Constant customer
            "order_type": "Sales",
            "transaction_date": data.get("order_date", nowdate()),
            "delivery_date": data.get("delivery_date", nowdate()),
            "po_no": data.get("order_id"),  # CS Cart Order ID
            "po_date": data.get("order_date", nowdate()),
            
            # Shipping Address
            "shipping_address_name": shipping_address.name,
            # "shipping_address": shipping_address.get_formatted_address(),
            
            # Custom fields for CS Cart integration
            "custom_cs_cart_order_id": data.get("order_id"),
            
            # Items - pass shipping address details for warehouse assignment
            "items": prepare_items(
                data.get("items", []),
                shipping_address_line1,
                shipping_address_line2,
                shipping_city,
                shipping_state,
                shipping_pincode
            ),
            
            # Pricing
            # "taxes_and_charges": get_tax_template(),
            # "taxes": prepare_taxes(data),
            
            # Additional fields
            "company": frappe.defaults.get_user_default("Company"),
            "currency": "INR",
            "selling_price_list": CS_CART_CONSTANTS.get("CUSTOMER_PRICE_LIST"),
            "custom_type": "B2C"
        })
        
        # Insert the Sales Order
        sales_order.insert(ignore_permissions=True)
        # Auto-submit Sales Order via Workflow before creating Pick List
        if frappe.db.get_single_value("CS Cart Settings", "auto_submit_so"):
            from frappe.model.workflow import apply_workflow
            
            try:
                apply_workflow(sales_order, "Submit for approval")
                apply_workflow(sales_order, "Approve")
            except Exception as e:
                frappe.log_error(f"Failed to auto-submit SO via Workflow: {str(e)}", "Workflow Auto-Submit Error")

        # Commit the transaction
        frappe.db.commit()

        # Silently create Draft Pick Lists for stock reservation.
        # Errors are only logged — SO creation must always return success.
        try:
            _create_reservation_pick_lists(sales_order)
        except Exception as e:
            print(e)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Pick List Reservation Failed (SO: {sales_order.name})"
            )

        return {
            "status": "success",
            "message": "Sales Order created successfully",
            "sales_order": sales_order.name,
            "sales_order_id": sales_order.name,
            "order_total": sales_order.grand_total
        }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"CS Cart Sales Order Creation Failed - {data.get('order_id', 'Unknown')}"
        )
        return {
            "status": "error",
            "message": str(e),
            "order_id": data.get("order_id")
        }


@frappe.whitelist()
def create_pick_lists_for_sales_order(sales_order_id, items=None):
    print("---------------------------------------")
    """
    API endpoint to create Pick Lists for a Sales Order and return warehouse details
    
    Args:
        sales_order_id: Name/ID of the Sales Order
        items: Optional list of items to validate against the Sales Order
    
    Returns:
        {
            "status": "success",
            "message": "Pick Lists created successfully",
            "sales_order": "SO-00001",
            "items": [
                {
                    "item_code": "ITM-001",
                    "qty": 2,
                    "warehouse": "Delhi Warehouse - DPL",
                    "warehouse_address": "123 Warehouse St, Delhi..."
                }
            ],
            "pick_lists": ["PL-00001", "PL-00002"]
        }
    """
    try:
        items_data = items
        
        # Parse sales_order_id if it's a JSON string
        if isinstance(sales_order_id, str):
            try:
                data = json.loads(sales_order_id)
                # If it's a dict, it might contain the ID and items
                if isinstance(data, dict):
                    sales_order_id = data.get("sales_order_id") or data.get("sales_order")
                    if not items_data:
                        items_data = data.get("items")
            except (json.JSONDecodeError, ValueError):
                # If it's not JSON, use it as-is
                pass
        
        # Validate sales order exists
        if not frappe.db.exists("Sales Order", sales_order_id):
            frappe.throw(_(f"Sales Order {sales_order_id} does not exist"))
        
        # Get the sales order
        sales_order = frappe.get_doc("Sales Order", sales_order_id)
        
        # Validate items if provided in payload
        if items_data:
            so_items_map = {}
            for item in sales_order.items:
                so_items_map[item.item_code] = so_items_map.get(item.item_code, 0.0) + flt(item.qty)
            
            payload_items_map = {}
            if isinstance(items_data, list):
                for item in items_data:
                    code = item.get("item_code")
                    qty = flt(item.get("qty"))
                    payload_items_map[code] = payload_items_map.get(code, 0.0) + qty
            
            # Check for mismatches
            mismatch = False
            error_msg = ""
            
            if len(so_items_map) != len(payload_items_map):
                mismatch = True
                error_msg = "Item count mismatch"
            else:
                for code, qty in so_items_map.items():
                    if code not in payload_items_map:
                        mismatch = True
                        error_msg = f"Item {code} missing in payload"
                        break
                    if payload_items_map[code] != qty:
                        mismatch = True
                        error_msg = f"Quantity mismatch for item {code}. Expected {qty}, got {payload_items_map[code]}"
                        break
            
            if mismatch:
                frappe.response["http_status_code"] = 400
                return {
                    "status": "error",
                    "message": f"Validation Failed: {error_msg}. Sales Order items do not match payload items.",
                    "sales_order": sales_order.name
                }
        
        # Validate addresses for all items before creating any pick lists
        address_errors = []
        checked_entities = set() # To avoid checking same warehouse/supplier multiple times
        for item in sales_order.items:
            fulfillment_type = (item.custom_fulfilled_by or "").lower()
            
            if fulfillment_type == 'brand':
                supplier = item.supplier
                if supplier and supplier not in checked_entities:
                    checked_entities.add(supplier)
                    address = get_address("Supplier", supplier)
                    if not address:
                        address_errors.append(f"Missing address for Supplier {supplier} (Item {item.item_code})")
            
            else: # Warehouse
                warehouse = item.warehouse
                if warehouse and warehouse not in checked_entities:
                    checked_entities.add(warehouse)
                    address = get_address("Warehouse", warehouse)
                    if not address:
                        address_errors.append(f"Missing address for Warehouse {warehouse} (Item {item.item_code})")

        if address_errors:
            error_message = "Address Verification Failed:\n" + "\n".join(sorted(list(set(address_errors))))
            frappe.throw(_(error_message))

        # Separate valid items and track logistic partners
        execution_errors = []
        valid_so_items = []
        item_partner_map = {}

        # Fetch item details including custom_b2c_product_id and supplier IDs
        so_item_codes = [d.item_code for d in sales_order.items]
        item_product_id_map = {}
        supplier_id_map = {} # Map[supplier_name] -> custom_supplier_id
        
        if so_item_codes:
            # 1. Fetch product IDs
            item_details = frappe.get_all("Item",
                filters={"name": ["in", so_item_codes]},
                fields=["name", "custom_b2c_product_id"]
            )
            for idetail in item_details:
                item_product_id_map[idetail.name] = idetail.custom_b2c_product_id
            
            # 2. Fetch Supplier IDs from Supplier doctype
            # Get unique suppliers from sales order items
            supplier_names = list(set([d.supplier for d in sales_order.items if d.supplier]))
            
            if supplier_names:
                suppliers = frappe.get_all("Supplier",
                    filters={"name": ["in", supplier_names]},
                    fields=["name", "custom_supplier_id"]
                )
                
                for sup in suppliers:
                    supplier_id_map[sup.name] = sup.custom_supplier_id

        for d in sales_order.items:
            fulfillment_type = (d.custom_fulfilled_by or "").lower()
            source_name = d.supplier if fulfillment_type == 'brand' else d.warehouse
            
            logistic_partner = None
            partner_id = None
            if source_name:
                logistic_partner = frappe.db.get_value("Supplier" if fulfillment_type == 'brand' else "Warehouse", 
                                                        source_name, "custom_default_logistic_partner")
                # Fetch partner_id from Logistic Partner doctype
                if logistic_partner:
                    partner_id = frappe.db.get_value("Logistic Partner", logistic_partner, "partner_id")
            
            if not logistic_partner:
                # Get address for the source (warehouse or supplier)
                source_address = get_address("Supplier" if fulfillment_type == 'brand' else "Warehouse", source_name) if source_name else ""
                
                error_obj = {
                    "item_code": d.item_code,
                    "product_code": d.get("customer_item_code"),
                    "product_id": item_product_id_map.get(d.item_code),
                    "qty": d.qty,
                    "sales_order_item": d.name,
                    "error": "Logistic partner not assigned",
                    "fulfillment_type": fulfillment_type,
                }
                
                # Add warehouse or supplier details based on fulfillment type
                if fulfillment_type == 'brand':
                    error_obj["supplier"] = source_name or "Not Set"
                    error_obj["supplier_address"] = source_address
                else:
                    error_obj["warehouse"] = source_name or "Not Set"
                    error_obj["warehouse_address"] = source_address
                
                execution_errors.append(error_obj)
                continue

            # Check for Product ID in Phase 2
            product_id = item_product_id_map.get(d.item_code)
            if not product_id:
                # Get address for the source (warehouse or supplier)
                source_address = get_address("Supplier" if fulfillment_type == 'brand' else "Warehouse", source_name) if source_name else ""
                
                error_obj = {
                    "item_code": d.item_code,
                    "product_code": d.get("customer_item_code"),
                    "product_id": None,
                    "qty": d.qty,
                    "sales_order_item": d.name,
                    "error": "Product ID not found",
                    "fulfillment_type": fulfillment_type,
                    "shipment_id": d.get("custom_shipment_id") if hasattr(d, "custom_shipment_id") else None
                }
                
                # Add warehouse or supplier details based on fulfillment type
                if fulfillment_type == 'brand':
                    error_obj["supplier"] = d.supplier
                    error_obj["supplier_address"] = source_address
                else:
                    error_obj["warehouse"] = source_name
                    error_obj["warehouse_address"] = source_address
                
                execution_errors.append(error_obj)
                continue

            item_partner_map[d.name] = {
                "logistic_partner": logistic_partner,
                "partner_id": partner_id
            }
            if fulfillment_type == 'warehouse':
                valid_so_items.append(d)

        # Pick Lists were already created in Step 1 (create_sales_order) for reservation.
        # No creation here — just read whatever exists for this SO.
        # (Items already in a pick list are naturally covered by pick_list_map below.)

        # Build item details with resolved warehouses and addresses for response
        
        # Track which items have errors (by sales_order_item name)
        errored_item_names = set()
        for error in execution_errors:
            if error.get("sales_order_item"):
                errored_item_names.add(error["sales_order_item"])
        
        # Build pick_list_map: SO item name -> Pick List name
        so_item_names = [d.name for d in sales_order.items]
        pick_list_map = {}
        if so_item_names:
            pick_list_items_data = frappe.get_all("Pick List Item",
                filters={"sales_order_item": ["in", so_item_names]},
                fields=["parent", "sales_order_item"]
            )
            for pli in pick_list_items_data:
                pick_list_map[pli.sales_order_item] = pli.parent

        # Collect unique Pick List names created in Step 1
        pick_lists_names = list(set(pick_list_map.values()))

        flagship_items = []
        pick_list_items = []

        for d in sales_order.items:
            # Skip items that are not in item_partner_map (already have logistic partner errors)
            if d.name not in item_partner_map:
                continue
            
            # Skip items that have any errors (including insufficient stock)
            if d.name in errored_item_names:
                continue

            warehouse_name = None
            warehouse_address = None
            fulfillment_type = (d.custom_fulfilled_by or "").lower()

            if fulfillment_type == 'brand':
                supplier = d.supplier
                if supplier:
                    warehouse_name = supplier
                    warehouse_address = get_address("Supplier", supplier)
                else:
                    # Fallback if no supplier is found (should not happen due to prepare_items validation)
                    warehouse_name = "Brand Fulfilled - No Supplier"
                    warehouse_address = ""

            else: # Warehouse fulfillment
                warehouse_name = d.warehouse
                if warehouse_name:
                    warehouse_address = get_address("Warehouse", warehouse_name)
                    
            # Check if warehouse item has a valid pick list
            pick_list_name = pick_list_map.get(d.name)
            if fulfillment_type != 'brand' and not pick_list_name:
                 # Error: Pick List not created for this warehouse item
                 execution_errors.append({
                     "item_code": d.item_code,
                     "product_code": d.get("customer_item_code"),
                     "product_id": item_product_id_map.get(d.item_code),
                     "qty": d.qty,
                     "sales_order_item": d.name,
                     "warehouse": warehouse_name,
                     "warehouse_address": warehouse_address,
                     "error": "Pick List creation failed",
                     "fulfillment_type": fulfillment_type,
                     "shipment_id": d.get("custom_shipment_id") if hasattr(d, "custom_shipment_id") else None
                 })
                 continue
            
            # [NEW] Validate Supplier ID for Brand fulfillment
            supplier_id = None
            if fulfillment_type == 'brand':
                supplier_id = supplier_id_map.get(d.supplier)
                if not supplier_id:
                    # Error: Supplier ID not found for this brand item
                    execution_errors.append({
                        "item_code": d.item_code,
                        "product_code": d.get("customer_item_code"),
                        "product_id": item_product_id_map.get(d.item_code),
                        "qty": d.qty,
                        "sales_order_item": d.name,
                        "supplier": d.supplier,
                        "supplier_address": warehouse_address, # warehouse_address variable holds supplier address for brand items
                        "error": "Supplier ID not found",
                        "fulfillment_type": fulfillment_type,
                        "shipment_id": d.get("custom_shipment_id") if hasattr(d, "custom_shipment_id") else None
                    })
                    continue
            
            # Build item details for the response
            partner_info = item_partner_map[d.name]
            item_dict = {
                "product_code": d.get("customer_item_code"),
                "item_code": d.item_code,
                "product_id": item_product_id_map.get(d.item_code),
                "qty": d.qty,
                "supplier": warehouse_name,
                "supplier_address": warehouse_address,
                "pick_list": pick_list_name,
                "custom_default_logistic_partner": partner_info.get("logistic_partner"),
                "partner_id": partner_info.get("partner_id"),
                "shipment_id": d.get("custom_shipment_id") if hasattr(d, "custom_shipment_id") else None
            }
            
            if supplier_id:
                item_dict["supplier_id"] = supplier_id

            if fulfillment_type == 'brand':
                item_dict["supplier"] = d.supplier
                item_dict["supplier_address"] = warehouse_address
                flagship_items.append(item_dict)
            else:
                pick_list_items.append(item_dict)
        
        # Commit the transaction
        frappe.db.commit()
        
        message = "Pick Lists created successfully"
        if not pick_lists_names:
            message = "No Pick Lists found"
        
        # Split errors into flagship_items and pick_list_items
        flagship_items_errors = []
        pick_list_items_errors = []
        
        for error in execution_errors:
            fulfillment_type = error.get("fulfillment_type", "").lower()
            if fulfillment_type == "brand":
                flagship_items_errors.append(error)
            else:
                pick_list_items_errors.append(error)
            
        return {
            "status": "success",
            "message": message,
            "sales_order": sales_order.name,
            "order_id": sales_order.po_no,
            "flagship_items": flagship_items,
            "pick_list_items": pick_list_items,
            "pick_lists": pick_lists_names,
            "errors": {
                "flagship_items": flagship_items_errors,
                "pick_list_items": pick_list_items_errors
            }
        }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Pick List Creation Failed - {sales_order_id}"
        )
        frappe.response["http_status_code"] = 500
        return {
            "status": "error",
            "message": str(e),
            "sales_order": sales_order_id
        }


def validate_data(data):
    """Validate incoming data"""
    required_fields = ["order_id", "delivery_address", "items"]

    for field in required_fields:
        if not data.get(field):
            frappe.throw(_(f"Missing required field: {field}"))

    # Validate delivery address
    address = data.get("delivery_address", {})
    required_address_fields = ["address_line1", "city", "state", "pincode", "country", "phone"]

    for field in required_address_fields:
        if not address.get(field):
            frappe.throw(_(f"Missing required address field: {field}"))

    # Validate items
    if not data.get("items") or len(data.get("items")) == 0:
        frappe.throw(_("At least one item is required"))

    for item in data.get("items"):
        if not item.get("item_code") or not item.get("qty"):
            frappe.throw(_("Each item must have item_code and qty"))


def get_address(doctype, docname):
    """Create or get shipping address"""
    
    """Return the first Shipping type address linked to the constant ERPNext
    customer ``Roadsky``.
    """

    # Fetch the earliest Shipping address linked to customer Roadsky
    shipping_address_name = frappe.db.sql(
        """
        SELECT a.name
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent = a.name
        WHERE dl.link_doctype = %s
          AND dl.link_name = %s
        ORDER BY a.creation ASC
        LIMIT 1
        """,
        (doctype, docname),
        as_dict=True,
    )
    print("shipping_address_name",shipping_address_name)

    if shipping_address_name:
        # return frappe.get_doc("Address", shipping_address_name[0].name)
        return frappe.db.get_value("Address", shipping_address_name[0].name,["name","address_title","address_type","address_line1","city","state","country","pincode","gstin","phone","email_id"],as_dict=True)

    # No Shipping address found for customer – abort and ask admin to create one
    print(doctype, docname)
    if doctype == "Supplier" or doctype == "Warehouse":
        return ""
    else:
        frappe.throw(_(f"No address found for {doctype} {docname}"))


def get_item_supplier(item_code):
    """
    Get the supplier from Item Supplier child table where custom_default_supplier is checked
    """
    supplier = frappe.db.get_value(
        "Item Supplier",
        {"parent": item_code, "custom_default_supplier": 1},
        "supplier"
    )
    return supplier


def prepare_items(items_data, shipping_address_line1=None, shipping_address_line2=None, 
                  shipping_city=None, shipping_state=None, shipping_pincode=None):
    """Prepare items for Sales Order with dynamic warehouse assignment"""
    items = []
    
    # Separate warehouse-fulfilled items from brand-fulfilled items
    warehouse_items = []
    print("DEBUG: items_data[0]:", items_data[0] if items_data else "Empty")
    
    for item in items_data:
        # Validate item exists in ERPNext
        if not frappe.db.exists("Item", item.get("item_code")):
            frappe.throw(_(f"Item {item.get('item_code')} does not exist in system"))
        
        # Get fulfillment type from Item master
        item_doc = frappe.get_cached_doc("Item", item.get("item_code"))
        fulfillment_type = item_doc.custom_fulfilled_by if hasattr(item_doc, 'custom_fulfilled_by') and item_doc.custom_fulfilled_by else "Warehouse"
        
        if (fulfillment_type or "").lower() == "warehouse":
            # Collect warehouse items for batch processing
            warehouse_items.append({
                "item_code": item.get("item_code"),
                "item_name": item.get("item_name"),
                "qty": flt(item.get("qty")),
                "rate": flt(item.get("rate")),
                "delivery_date": item.get("delivery_date", nowdate()),
                "fulfillment_type": fulfillment_type,
                "customer_item_code": item.get("customer_item_code") or item.get("product_code")
            })
        elif (fulfillment_type or "").lower() == "brand":
            # Handle brand-fulfilled items
            supplier = item.get("supplier")
            if not supplier:
                supplier = get_item_supplier(item.get("item_code"))
            if not supplier:
                frappe.throw(_(f"Item {item.get('item_code')} is Brand fulfilled but has no supplier defined."))
            
            items.append({
                "item_code": item.get("item_code"),
                "item_name": item.get("item_name"),
                "qty": flt(item.get("qty")),
                "rate": flt(item.get("rate")),
                "warehouse": None,
                "delivery_date": item.get("delivery_date", nowdate()),
                "custom_fulfilled_by": fulfillment_type,
                "delivered_by_supplier": 1,
                "supplier": supplier,
                "customer_item_code": item.get("customer_item_code") or item.get("product_code")
            })
    
    # Process warehouse items using find_nearest_warehouse_with_inventory
    if warehouse_items and shipping_address_line1:
        try:
            # Import the function from logistics
            from kindlife_app.api.logistics import find_nearest_warehouse_with_inventory
            
            # Prepare items in the format expected by find_nearest_warehouse_with_inventory
            items_for_warehouse_lookup = [
                {"item_code": item["item_code"], "qty": item["qty"]} 
                for item in warehouse_items
            ]
            
            # Get warehouse assignments
            warehouse_assignments = find_nearest_warehouse_with_inventory(
                items=items_for_warehouse_lookup,
                shipping_address_line1=shipping_address_line1,
                shipping_address_line2=shipping_address_line2,
                shipping_city=shipping_city,
                shipping_state=shipping_state,
                shipping_pincode=shipping_pincode
            )
            
            # Create a mapping of item_code to warehouse assignment
            warehouse_map = {}
            if warehouse_assignments and isinstance(warehouse_assignments, list):
                for assignment in warehouse_assignments:
                    warehouse_map[assignment.get("item_code")] = assignment.get("warehouse_id")
            
            # Add warehouse items with assigned warehouses
            for item in warehouse_items:
                warehouse = warehouse_map.get(item["item_code"])
                if not warehouse:
                    # Fallback to hardcoded warehouse if assignment fails
                    warehouse = get_item_warehouse(item["item_code"])
                    frappe.msgprint(_(f"Warning: Could not assign warehouse for item {item['item_code']}, using fallback warehouse {warehouse}"))
                
                items.append({
                    "item_code": item["item_code"],
                    "item_name": item["item_name"],
                    "qty": item["qty"],
                    "rate": item["rate"],
                    "warehouse": warehouse,
                    "delivery_date": item["delivery_date"],
                    "custom_fulfilled_by": item["fulfillment_type"],
                    "delivered_by_supplier": 0,
                    "supplier": None,
                    "customer_item_code": item.get("customer_item_code")
                })
        except Exception as e:
            # If warehouse assignment fails, fall back to hardcoded logic
            frappe.log_error(
                message=f"Error in warehouse assignment: {str(e)}\n{frappe.get_traceback()}",
                title="Warehouse Assignment Error"
            )
            frappe.msgprint(_(f"Warning: Warehouse assignment failed, using fallback logic. Error: {str(e)}"))
            
            # Add items with fallback warehouse
            for item in warehouse_items:
                warehouse = get_item_warehouse(item["item_code"])
                items.append({
                    "item_code": item["item_code"],
                    "item_name": item["item_name"],
                    "qty": item["qty"],
                    "rate": item["rate"],
                    "warehouse": warehouse,
                    "delivery_date": item["delivery_date"],
                    "custom_fulfilled_by": item["fulfillment_type"],
                    "delivered_by_supplier": 0,
                    "supplier": None,
                    "customer_item_code": item.get("customer_item_code")
                })
    else:
        # If no shipping address provided, use fallback logic
        for item in warehouse_items:
            warehouse = get_item_warehouse(item["item_code"])
            items.append({
                "item_code": item["item_code"],
                "item_name": item["item_name"],
                "qty": item["qty"],
                "rate": item["rate"],
                "warehouse": warehouse,
                "delivery_date": item["delivery_date"],
                "custom_fulfilled_by": item["fulfillment_type"],
                "delivered_by_supplier": 0,
                "supplier": None,
                "customer_item_code": item.get("customer_item_code")
            })
    
    return items


def get_item_warehouse(item_code):
    """Determine warehouse for an item.

    Fallback implementation – returns the default warehouse when dynamic assignment fails.
    This is used as a safety net when find_nearest_warehouse_with_inventory cannot determine
    the optimal warehouse.
    """
    # Fallback to default warehouse
    return "Edgistify - Dwarka - DPL"


def prepare_taxes(data):
    """Prepare taxes for Sales Order"""
    taxes = []
    
    # Add delivery charges if provided
    if data.get("delivery_charges"):
        taxes.append({
            "charge_type": "Actual",
            "account_head": "Freight and Forwarding Charges - D",  # Update with your account
            "description": "Delivery Charges",
            "tax_amount": flt(data.get("delivery_charges"))
        })
    
    # Add tax amount if provided
    if data.get("tax_amount"):
        taxes.append({
            "charge_type": "Actual",
            "account_head": "Output Tax CGST - D",  # Update with your account
            "description": "GST",
            "tax_amount": flt(data.get("tax_amount"))
        })
    
    # Add discount if provided
    if data.get("discount_amount"):
        taxes.append({
            "charge_type": "Actual",
            "account_head": "Discount - D",  # Update with your account
            "description": "Discount",
            "tax_amount": -flt(data.get("discount_amount"))
        })
    
    return taxes


def get_tax_template():
    """Get default tax template"""
    # Return your default sales tax template
    # Update this based on your ERPNext setup
    return frappe.db.get_value("Sales Taxes and Charges Template", 
                               {"is_default": 1}, 
                               "name")


def _create_reservation_pick_lists(sales_order):
    """
    Create Draft Pick Lists immediately after SO creation for stock reservation.

    Called from ``create_sales_order`` (Step 1). Errors are logged by the
    caller but are never raised so SO creation always succeeds regardless of
    stock availability.
    """
    warehouse_items = [
        d for d in sales_order.items
        if (d.custom_fulfilled_by or "").lower() == "warehouse"
    ]
    if not warehouse_items:
        return

    pick_lists, errors = create_pick_lists(sales_order, items=warehouse_items)
    if errors:
        frappe.log_error(
            message=frappe.as_json(errors),
            title=f"Pick List Reservation Errors (SO: {sales_order.name})"
        )


def create_pick_lists(sales_order, items=None):
    """Create pick lists for warehouse fulfillment items"""
    pick_lists = []
    errors = []
    
    # Group items by warehouse
    warehouse_items = {}
    
    source_items = items if items is not None else sales_order.items

    for item in source_items:
        # Only create pick list for warehouse fulfillment (case-insensitive check)
        fulfillment_type = (item.custom_fulfilled_by or "").lower()
        if fulfillment_type == "warehouse":
            if item.warehouse not in warehouse_items:
                warehouse_items[item.warehouse] = []
            warehouse_items[item.warehouse].append(item)
    
    # If no warehouse items found, return empty list (Brand items don't need pick lists)
    if not warehouse_items:
        frappe.logger().info(f"No warehouse items found in Sales Order {sales_order.name} - may contain only Brand fulfillment items")
        return pick_lists, errors
    
    # Create pick list for each warehouse
    for warehouse, items_in_warehouse in warehouse_items.items():
        pick_list = frappe.get_doc({
            "doctype": "Pick List",
            "company": sales_order.company,
            "customer": sales_order.customer,
            "purpose": "Delivery",
            "locations": prepare_pick_list_items(items_in_warehouse, sales_order),
            "custom_sales_order": sales_order.name,
            "parent_warehouse": warehouse,
            "custom_type": "B2C"
        })
        
        # Set item locations and validate stock availability
        pick_list.set_item_locations()
        
        # Check for stock errors and record them
        insufficient_items = validate_pick_list_quantities(pick_list, items_in_warehouse)
        for item in insufficient_items:
            # Get warehouse address
            warehouse_address = get_address("Warehouse", warehouse)
            
            # Get product_code (customer_item_code) and sales_order_item name from sales order item
            product_code = None
            sales_order_item_name = None
            for so_item in items_in_warehouse:
                if so_item.item_code == item['item_code']:
                    product_code = so_item.get("customer_item_code")
                    sales_order_item_name = so_item.name
                    break
            
            errors.append({
                "item_code": item['item_code'],
                "product_code": product_code,
                "sales_order_item": sales_order_item_name,
                "error": "Insufficient stock",
                "qty": item['qty'],
                "available_qty": item['available_qty'],
                "warehouse": warehouse,
                "warehouse_address": warehouse_address,
                "fulfillment_type": "warehouse"
            })

        # Check if any locations were set
        if not pick_list.locations or len(pick_list.locations) == 0:
            continue
        
        pick_list.insert(ignore_permissions=True)
        pick_list.save()
        pick_lists.append(pick_list)
    
    return pick_lists, errors


def prepare_pick_list_items(items, sales_order):
    """Prepare items for pick list"""
    pick_items = []
    
    for item in items:
        # Get batch information if item is batched
        batch = get_available_batch(item.item_code, item.warehouse, item.qty)
        
        pick_items.append({
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "stock_qty": item.qty,
            # "warehouse": item.warehouse,
            "batch_no": batch,
            "sales_order": sales_order.name,
            "sales_order_item": item.name,
        })
    
    return pick_items


def validate_pick_list_quantities(pick_list, requested_items):
    """
    Validate that pick list has sufficient quantities for all requested items.
    Returns list of insufficient items instead of throwing.
    """
    # Group pick list locations by item
    picked_quantities = {}
    for location in pick_list.locations:
        if location.item_code not in picked_quantities:
            picked_quantities[location.item_code] = 0
        picked_quantities[location.item_code] += flt(location.qty)
    
    # Check each requested item
    insufficient_items = []
    for item in requested_items:
        picked_qty = picked_quantities.get(item.item_code, 0)
        if picked_qty < item.qty:
            insufficient_items.append({
                "item_code": item.item_code,
                "qty": item.qty,
                "available_qty": picked_qty,
                "warehouse": item.warehouse
            })
    
    return insufficient_items


def get_available_batch(item_code, warehouse, qty):
    """Get available batch for item"""
    batches = frappe.db.sql("""
        SELECT batch_no, SUM(actual_qty) as available_qty
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s 
        AND warehouse = %s
        AND batch_no IS NOT NULL
        AND actual_qty > 0
        GROUP BY batch_no
        HAVING available_qty >= %s
        ORDER BY creation ASC
        LIMIT 1
    """, (item_code, warehouse, qty), as_dict=1)
    
    return batches[0].batch_no if batches else None


def get_warehouse_address(warehouse):
    """Get formatted address from Warehouse doctype"""
    if not warehouse:
        return None
    
    try:
        # Get warehouse details including address
        warehouse_doc = frappe.get_cached_doc("Warehouse", warehouse)
        
        # Check if warehouse has an address linked
        if warehouse_doc.address:
            address_doc = frappe.get_doc("Address", warehouse_doc.address)
            return address_doc.get_display()
        
        # If no address linked, build from warehouse fields if available
        address_parts = []
        
        if hasattr(warehouse_doc, 'address_line_1') and warehouse_doc.address_line_1:
            address_parts.append(warehouse_doc.address_line_1)
        if hasattr(warehouse_doc, 'address_line_2') and warehouse_doc.address_line_2:
            address_parts.append(warehouse_doc.address_line_2)
        if hasattr(warehouse_doc, 'city') and warehouse_doc.city:
            address_parts.append(warehouse_doc.city)
        if hasattr(warehouse_doc, 'state') and warehouse_doc.state:
            address_parts.append(warehouse_doc.state)
        if hasattr(warehouse_doc, 'pin') and warehouse_doc.pin:
            address_parts.append(warehouse_doc.pin)
        
        if address_parts:
            return ", ".join(address_parts)
        
        # Return warehouse name if no address available
        return warehouse
        
    except Exception as e:
        frappe.log_error(
            message=f"Error fetching warehouse address for {warehouse}: {str(e)}",
            title="Warehouse Address Fetch Error"
        )
        return warehouse


# Webhook endpoint for CS Cart
@frappe.whitelist(allow_guest=True)
def cs_cart_webhook():
    """
    Webhook endpoint for CS Cart
    Validates API key and processes the request
    """
    try:
        # Get API key from header
        api_key = frappe.get_request_header("X-API-Key")
        
        # Validate API key
        if not validate_api_key(api_key):
            frappe.throw(_("Invalid API Key"), frappe.AuthenticationError)
        
        # Get request data
        data = frappe.local.form_dict
        
        # Create sales order
        result = create_sales_order(data)
        
        return result
        
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="CS Cart Webhook Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }


def validate_api_key(api_key):
    """Validate API key"""
    # Store API keys in a custom doctype or settings
    stored_key = frappe.db.get_single_value("CS Cart Settings", "api_key")
    return api_key == stored_key


# Utility function to get order status
@frappe.whitelist()
def get_order_status(order_id):
    """Get status of CS Cart order"""
    try:
        sales_order = frappe.db.get_value(
            "Sales Order",
            {"custom_cs_cart_order_id": order_id},
            ["name", "status", "per_delivered", "per_billed"],
            as_dict=1
        )
        
        if not sales_order:
            return {
                "status": "error",
                "message": "Order not found"
            }
        
        # Get pick list status
        pick_lists = frappe.get_all(
            "Pick List",
            filters={"custom_sales_order": sales_order.name},
            fields=["name", "status"]
        )
        
        return {
            "status": "success",
            "order_id": order_id,
            "sales_order": sales_order.name,
            "order_status": sales_order.status,
            "delivery_progress": sales_order.per_delivered,
            "billing_progress": sales_order.per_billed,
            "pick_lists": pick_lists
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def get_draft_pick_lists_count(sales_order):
    """
    Get count of draft and submitted Pick Lists linked to a Sales Order
    Also returns all linked Pick Lists, Delivery Notes, and Sales Invoices with status for display
    Returns:
        - draft_count: Number of draft Pick Lists
        - submitted_count: Number of submitted Pick Lists
        - draft_names: List of draft Pick List names
        - submitted_names: List of submitted Pick List names
        - all_pl_data: All Pick List data with status (for display)
        - all_dn_data: All Delivery Note data with status (for display)
        - all_si_data: All Sales Invoice data with status (for display)
    Uses frappe.get_list to respect permission queries
    """
    if not sales_order:
        return {
            "draft_count": 0,
            "submitted_count": 0,
            "draft_names": [],
            "submitted_names": [],
            "all_pl_data": [],
            "all_dn_data": [],
            "all_si_data": []
        }
    
    # Get all Pick List Items linked to this SO
    pl_items = frappe.get_all(
        'Pick List Item',
        filters={'sales_order': sales_order},
        fields=['parent'],
        distinct=True
    )
    pl_names = [item.parent for item in pl_items]
    
    draft_pick_lists = []
    submitted_pick_lists = []
    all_pl_data = []
    
    if pl_names:
        # Get all Pick Lists (draft + submitted, exclude cancelled)
        all_pick_lists = frappe.get_list(
            'Pick List',
            filters={
                'name': ['in', pl_names],
                'docstatus': ['!=', 2]
            },
            fields=['name', 'docstatus', 'status', 'workflow_state'],
            order_by='creation desc'
        )
        
        # Separate draft and submitted
        draft_pick_lists = [pl for pl in all_pick_lists if pl.docstatus == 0]
        submitted_pick_lists = [pl for pl in all_pick_lists if pl.docstatus == 1]
        
        # Store all Pick List data for display and add item details
        all_pl_data = all_pick_lists
        
        # Add item details for each Pick List
        for pl in all_pl_data:
            pl_items = frappe.get_all(
                'Pick List Item',
                filters={'parent': pl.name, 'sales_order': sales_order},
                fields=['item_code', 'warehouse', 'qty', 'picked_qty'],
                order_by='idx'
            )
            pl['items'] = pl_items
    
    # Get all Delivery Note Items linked to this SO
    dn_items = frappe.get_all(
        'Delivery Note Item',
        filters={'against_sales_order': sales_order},
        fields=['parent'],
        distinct=True
    )
    dn_names = [item.parent for item in dn_items]
    
    all_dn_data = []
    
    if dn_names:
        # Get all Delivery Notes (draft + submitted, exclude cancelled)
        all_dn_data = frappe.get_list(
            'Delivery Note',
            filters={
                'name': ['in', dn_names],
                'docstatus': ['!=', 2]
            },
            fields=['name', 'docstatus', 'status', 'is_return', 'posting_date'],
            order_by='creation desc'
        )
        
        # Add item details for each Delivery Note
        for dn in all_dn_data:
            dn_items = frappe.get_all(
                'Delivery Note Item',
                filters={'parent': dn.name, 'against_sales_order': sales_order},
                fields=['item_code', 'qty'],
                order_by='idx'
            )
            dn['items'] = dn_items
    
    # Get all Sales Invoice Items linked to this SO
    si_items = frappe.get_all(
        'Sales Invoice Item',
        filters={'sales_order': sales_order},
        fields=['parent'],
        distinct=True
    )
    si_names = [item.parent for item in si_items]
    
    all_si_data = []
    
    if si_names:
        # Get all Sales Invoices (draft + submitted, exclude cancelled)
        try:
            all_si_data = frappe.get_list(
                'Sales Invoice',
                filters={
                    'name': ['in', si_names],
                    'docstatus': ['!=', 2]
                },
                fields=['name', 'docstatus', 'status', 'is_return', 'posting_date', 'grand_total'],
                order_by='creation desc'
            )
        except frappe.exceptions.PermissionError as e:
            all_si_data = []
        
        # Add item details for each Sales Invoice
        for si in all_si_data:
            si_items = frappe.get_all(
                'Sales Invoice Item',
                filters={'parent': si.name, 'sales_order': sales_order},
                fields=['item_code', 'qty'],
                order_by='idx'
            )
            si['items'] = si_items
    
    return {
        "draft_count": len(draft_pick_lists),
        "submitted_count": len(submitted_pick_lists),
        "draft_names": [pl.name for pl in draft_pick_lists],
        "submitted_names": [pl.name for pl in submitted_pick_lists],
        "all_pl_data": all_pl_data,
        "all_dn_data": all_dn_data,
        "all_si_data": all_si_data
    }


def update_shipment_pdf_url(sales_order_id, shipment_id, file_url=None, shipped_items=None, awb_number=None):
    """
    Update the custom_shipment_document and custom_awb_number fields on Sales Order Item rows.
    
    AWB follows 'Last Call Wins' logic (always overwrites).
    PDF URL only updates if provided.
    """
    if not shipped_items and not awb_number:
        return 0

    # Ensure shipped_items is a list
    if isinstance(shipped_items, str):
        # Support comma-separated strings (common in REST clients)
        shipped_items = [s.strip() for s in shipped_items.split(",") if s.strip()]
    
    if not isinstance(shipped_items, list) or not shipped_items:
        return 0

    # Convert shipment_id to string for comparison since custom_shipment_id is a Data field
    shipment_id_str = str(shipment_id)

    # Use 'IN' clause for item codes
    item_placeholders = ', '.join(['%s'] * len(shipped_items))
    
    # Build filters for identifying the correct Sales Order Item rows
    filters = {
        "parent": sales_order_id,
        "custom_shipment_id": shipment_id_str,
        "item_code": ["in", shipped_items]
    }

    # Prepare values for update
    update_values = {"custom_awb_number": awb_number}
    if file_url:
        update_values["custom_shipment_document"] = file_url

    # Perform the update using the ORM-safe method
    frappe.db.set_value("Sales Order Item", filters, update_values, update_modified=False)

    # Get the count of updated rows for the response
    count_filters = filters.copy()
    if file_url:
        count_filters["custom_shipment_document"] = file_url
    
    updated_count = frappe.db.count("Sales Order Item", count_filters)

    # Propagate to linked PL, DN, PO
    sync_shipment_docs_for_so(sales_order_id)

    return updated_count



@frappe.whitelist()
def store_shipment_pdf(sales_order_id, shipment_id, shipped_items=None, pdf_file=None, carrier=None, tracking_number=None, awb_number=None):
    """
    API endpoint to store a shipment PDF in the File doctype.

    Args:
        sales_order_id (str): Name/ID of the Sales Order (alphanumeric)
        shipment_id (int): Shipment ID (integer)
        shipped_items (list|str): Item code(s) included in the shipment (Mandatory)
        pdf_file (str): Base64-encoded PDF content (Optional if awb_number present)
        carrier (str): Carrier name (Optional)
        tracking_number (int|str): Tracking number (Optional)
        awb_number (str): AWB number (Optional if pdf_file present)

    Example Payload:
    {
        "sales_order_id": "SAL-ORD-2025-001",
        "shipment_id": "123456",
        "shipped_items": ["ITEM-001", "ITEM-002"],
        "awb_number": "AWB_123456",
        "pdf_file": "JVBERi0xLjQK..." 
    }

    The PDF is saved as: Shipment_{sales_order_id}_{shipment_id}.pdf
    and attached to the Sales Order provided.
    """
    try:
        # --- Validate required fields ---
        if not sales_order_id:
            frappe.throw(_("Missing required field: sales_order_id"))
        if not shipment_id:
            frappe.throw(_("Missing required field: shipment_id"))
        
        # shipped_items must be provided and non-empty
        if not shipped_items:
            frappe.throw(_("Missing required field: shipped_items"))
        
        # At least one of PDF or AWB must be present
        if not pdf_file and not awb_number:
            frappe.throw(_("Either pdf_file or awb_number must be provided"))

        # --- Validate Sales Order exists and is not cancelled ---
        so_status = frappe.db.get_value("Sales Order", sales_order_id, "docstatus")
        if so_status is None:
            frappe.throw(_(f"Sales Order {sales_order_id} does not exist"))
        if so_status == 2:
            frappe.throw(_(f"Sales Order {sales_order_id} is cancelled"))

        file_url = None
        if pdf_file:
            # --- Decode the Base64 PDF ---
            try:
                pdf_content = base64.b64decode(pdf_file)
            except Exception:
                frappe.throw(_("Invalid Base64 string provided for pdf_file"))

            # --- Build file name ---
        # User requested to use Sales Order name instead of po_name
            file_name = f"Shipment_{sales_order_id}_{shipment_id}.pdf"

            # --- Save to File doctype ---
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": file_name,
                "content": pdf_content,
                "is_private": 1,
                "attached_to_doctype": "Sales Order",
                "attached_to_name": sales_order_id
            })
            file_doc.save(ignore_permissions=True)
            file_url = file_doc.file_url

        # Update matching child table rows
        rows_updated = update_shipment_pdf_url(sales_order_id, shipment_id, file_url, shipped_items, awb_number)

        frappe.db.commit()

        return {
            "status": "success",
            "message": "Shipment PDF stored successfully" if pdf_file else "AWB updated successfully",
            "file_name": file_doc.file_name if pdf_file else None,
            "file_url": file_url,
            "sales_order": sales_order_id,
            "shipment_id": shipment_id,
            "attached_to": f"Sales Order: {sales_order_id}",
            "rows_updated": rows_updated
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Shipment PDF Storage Failed - SO: {sales_order_id}, Shipment: {shipment_id}"
        )
        return {
            "status": "error",
            "message": str(e),
            "sales_order": sales_order_id,
            "shipment_id": shipment_id,
        }

