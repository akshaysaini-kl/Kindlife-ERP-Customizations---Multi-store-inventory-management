import frappe
import json

@frappe.whitelist()
def get_price_lists_for_supplier(supplier):
    results = frappe.get_all(
        'Item Price',
        filters={'supplier': supplier},
        fields=['DISTINCT price_list']
    )
    return [r.price_list for r in results]



@frappe.whitelist()
def create_item_with_custom_suppliers(item_data):#This is the json sent by user
    """
        Fields set
            - custom_b2c_product_id
            - item_name
            - item_group
            - stock_uom
            - description
            - custom_mrp
            - gst_hsn_code
            - custom_ean
            - custom_type


        Structure
            {
                "item_data":[
                    {
                        "custom_b2c_product_id": "1010",
                        "item_name": "New Product 1991",
                        "description": "testing for multiple suppliers",
                        "custom_mrp": 12.0,
                        "item_group": "Cleansers",
                        "gst_hsn_code": "010121111",
                        "supplier_items": [
                        {"supplier_id": "123", "supplier_part_no": "ABC-XYZ-100"}
                        ],
                        "custom_type": "B2C"
                    },
                        {
                        "custom_b2c_product_id": "1010",
                        "item_name": "New Product 1991",
                        "description": "testing for multiple suppliers",
                        "custom_mrp": 12.0,
                        "item_group": "Cleansers",
                        "gst_hsn_code": "010121",
                        "supplier_items": [
                            {"supplier_id": "123", "supplier_part_no": "ABC-XYZ-100"}
                        ],
                        "custom_type": "B2C"
                    }
                ]
            }
    """
    print("item_data --> ",item_data)
    created = []

    try:
        for idx, single in enumerate(item_data):
            try:
                # 1. Process the supplier list to replace supplier_id with the real supplier name
                processed_supplier_items = []
                for supplier_info in single.get("supplier_items", []):
                    supplier_id = supplier_info.get("supplier_id")
                    if not supplier_id:
                        frappe.throw(f"Missing 'supplier_id' in supplier data: {supplier_info}")

                    supplier_name = frappe.db.get_value("Supplier", {"custom_supplier_id": supplier_id}, "name")


                    if not supplier_name:
                        frappe.throw(f"Supplier with custom ID '{supplier_id}' not found in the system.")
                    
                    processed_supplier_items.append({
                        "supplier": supplier_name,
                        "supplier_part_no": supplier_info.get("supplier_part_no")
                    })

                # 2. Create a new Item document in memory
                new_item = frappe.new_doc("Item")
                
                # 3. Map the data
                new_item.custom_b2c_product_id = single.get("custom_b2c_product_id")
                new_item.item_name = single.get("item_name")
                new_item.item_group = single.get("item_group")
                new_item.stock_uom = single.get("stock_uom", "Pcs") 
                new_item.description = single.get("description")
                new_item.custom_mrp = single.get("custom_mrp")
                new_item.gst_hsn_code = single.get("gst_hsn_code")
                new_item.custom_ean = single.get("custom_ean")
                new_item.custom_type = single.get("custom_type")


                # 4. Add the processed child table data
                print("processed_supplier_items --> ",processed_supplier_items)
                new_item.set("supplier_items", processed_supplier_items)

                # 5. Save the document to the database
                new_item.insert(ignore_permissions=True) # Use with caution, good for system integrations
                created.append({"item_name": new_item.item_name, "item": new_item.name})
                frappe.db.commit()
            except Exception as e:
                item_ident = single.get("item_name") 
                frappe.throw(f"Error processing item at index {idx+1} (item: {item_ident}): {e}")



        return {"status": "success", "created": created}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Item API Error")
        frappe.response.http_status_code = 500
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_items_by_ref_code(data=None):
    """
    Fetch unique Item Codes for items that have a matching ref_code in their customer_items table.
    Supports both JSON body and standard form-data/query parameters.
    """
    try:
        # 1. Parse data (Standard robust pattern used in sales_order.py)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass

        # 2. Extract ref_code from JSON or fallback to query params
        ref_code = None
        if isinstance(data, dict):
            ref_code = data.get("ref_code")
        else:
            # Fallback if passed as a single string argument or query param
            ref_code = data or frappe.form_dict.get("ref_code")

        if not ref_code:
            return {"status": "error", "message": "ref_code is required"}

        item_codes = frappe.db.sql("""
            SELECT DISTINCT parent 
            FROM `tabItem Customer Detail` 
            WHERE ref_code = %s
        """, (ref_code,), as_dict=True)

        return {
            "status": "success",
            "count": len(item_codes),
            "data": [d.parent for d in item_codes]
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Items by Ref Code API Error")
        return {"status": "error", "message": str(e)}
