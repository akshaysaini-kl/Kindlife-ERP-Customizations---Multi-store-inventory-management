
# my_custom_app/customizations/item_dashboard.py

from erpnext.stock.doctype.item.item_dashboard import get_data as original_get_data
import frappe
from frappe import _
from kindlife_app.services.cscart_service import CSCartAPI
import re

def get_item_dashboard_data(data):
    remove_map = {
        "Groups": ["BOM", "Product Bundle", "Item Alternative"],
        "Manufacture": ["Production Plan", "Work Order", "Item Manufacturer"]
    }

    # Go through each transaction group and filter items
    filtered_transactions = []
    for txn_group in data.get("transactions", []):
        label = txn_group.get("label")
        items = txn_group.get("items", [])

        if label in remove_map:
            # Remove unwanted items from this group
            items = [item for item in items if item not in remove_map[label]]

        # Only add the group back if there are still items left
        if items:
            filtered_transactions.append({
                "label": label,
                "items": items
            })

    data["transactions"] = filtered_transactions
    return data


def before_insert(doc, method):
    # For Kindlife, even variants should use Naming Series to get sequential codes
    if doc.variant_of:
        from frappe.model.naming import set_name_by_naming_series
        from frappe.utils import strip
        
        if not doc.naming_series:
            # If naming_series is not set, try to get it from template
            doc.naming_series = frappe.db.get_value("Item", doc.variant_of, "naming_series")
            
        if not doc.naming_series:
            # Fallback to the default property from meta
            doc.naming_series = frappe.get_meta("Item").get_field("naming_series").default
            
        if doc.naming_series:
            # Generate the next name in the series
            set_name_by_naming_series(doc)
            # Sync item_code with the newly generated sequential name
            doc.item_code = strip(doc.name)
            doc.name = doc.item_code

def validate(doc, method):
    #  This function removes extra space from name
    normalize_item_name(doc)
    validate_item_integrity(doc)
    validate_ean(doc)
    validate_prohibited_words(doc)
    validate_brand_item_uniqueness(doc)
    set_supplier_skus(doc)
    validate_default_supplier(doc)
    set_cs_cart_product_code(doc)
    validate_ean_uniqueness(doc)
    validate_supplier_items(doc)
    validate_customer_items(doc)
    validate_mrp_edit(doc)
    validate_variant_attributes(doc)

def validate_variant_attributes(doc):
    """Simple variant validation: block variant-of-variant and illegal attributes"""
    if not doc.variant_of:
        return

    # Check 1: variant_of must point to a template, not another variant
    parent_item = frappe.db.get_value("Item", doc.variant_of, "variant_of")
    if parent_item:
        frappe.throw(_("Item {0} is a variant and cannot be used as a template").format(frappe.bold(doc.variant_of)))

    # Check 2: all attributes must be declared on the template
    template_doc = frappe.get_doc("Item", doc.variant_of)
    template_attr_names = {row.attribute for row in template_doc.attributes}

    doc_attr_names = {row.attribute for row in doc.attributes if row.attribute}
    illegal = doc_attr_names - template_attr_names

    if illegal:
        frappe.throw(_("Attributes {0} are not defined on template {1}").format(
            ", ".join(frappe.bold(a) for a in illegal),
            frappe.bold(doc.variant_of)
        ))

def validate_mrp_edit(doc):
    if frappe.db.get_single_value("Kindlife Settings", "allow_mrp_edit"):
        return

    if not doc.is_new():
        old_mrp = frappe.db.get_value("Item", doc.name, "custom_mrp")
        if old_mrp is not None and float(old_mrp) != float(doc.custom_mrp or 0):
            frappe.throw(_("MRP cannot be edited directly. Please use the 'Edit MRP' button under Actions."))



def set_cs_cart_product_code(doc):
    if not doc.get("custom_cs_cart_product_code") and doc.get("custom_ean"):
        doc.custom_cs_cart_product_code = doc.custom_ean

def validate_ean_uniqueness(doc):
    ean = doc.get("custom_ean")
    if not ean:
        return

    # Base filters for same EAN and different record
    filters = {
        "custom_ean": ean,
        "name": ["!=", doc.name]
    }
    
    # Check for duplicates
    duplicates = frappe.get_all("Item", filters=filters, fields=["name", "variant_of"])
    
    offending_items = []
    for dupe in duplicates:
        # ALLOW if:
        # 1. Current doc is a variant and dupe is its template
        if doc.variant_of and dupe.name == doc.variant_of:
            continue
        # 2. Current doc is a variant and dupe is a sibling variant (same template)
        if doc.variant_of and dupe.variant_of == doc.variant_of:
            continue
        # 3. Current doc is a template and dupe is its variant
        if not doc.variant_of and dupe.variant_of == doc.name:
            continue
            
        # Otherwise, collect offending item
        offending_items.append(dupe.name)
    
    if offending_items:
        links = [frappe.utils.get_link_to_form("Item", name) for name in offending_items]
        frappe.throw(
            _("EAN must be unique unless items are variants of the same template.<br>Items with EAN {0}: {1}").format(ean, ", ".join(links)),
            frappe.ValidationError
        )

def validate_default_supplier(doc):
    if not doc.supplier_items:
        return
        
    if len(doc.supplier_items) == 1:
        # If there is only one row, it should automatically be set as default
        doc.supplier_items[0].custom_default_supplier = 1
    else:
        # If there are multiple rows, ensure only one is selected
        default_count = sum(1 for item in doc.supplier_items if item.custom_default_supplier)
        if default_count > 1:
            frappe.throw(_("Only one supplier can be selected as Default Supplier"), frappe.ValidationError)

def normalize_item_name(doc):
    if doc.item_name:
        doc.item_name = " ".join(doc.item_name.split())

def validate_supplier_items(doc):
    if not doc.get("supplier_items"):
        return

    # 1. One item cannot have same supplier multiple times
    seen_suppliers = set()
    for row in doc.supplier_items:
        if not row.supplier:
            continue
        if row.supplier in seen_suppliers:
            frappe.throw(_("Supplier '{0}' is appearing twice in the supplier table").format(row.supplier))
        seen_suppliers.add(row.supplier)

    # 2. One supplier cannot have same sku for multiple item
    for row in doc.supplier_items:
        if not row.supplier or not row.supplier_part_no:
            continue
        
        # Exclude SKU "0" from uniqueness validation
        if str(row.supplier_part_no).strip() == "0":
            continue

        # Check if another Item has the same supplier and supplier_part_no
        filters = {
            "supplier": row.supplier,
            "supplier_part_no": row.supplier_part_no,
            "parent": ["!=", doc.name],
            "parenttype": "Item"
        }
        
        duplicate_item_suppliers = frappe.get_all(
            "Item Supplier",
            filters=filters,
            fields=["parent", "supplier", "supplier_part_no"]
        )
        
        if duplicate_item_suppliers:
            unique_items = list(set([d.parent for d in duplicate_item_suppliers]))
            items_list_html = "<ul>" + "".join([f"<li>{item}</li>" for item in unique_items]) + "</ul>"
            frappe.throw(
                _("Supplier '{0}' already has the SKU '{1}' assigned to the following items:<br>{2}").format(
                    row.supplier, row.supplier_part_no, items_list_html
                )
            )

def validate_customer_items(doc):
    if not doc.get("customer_items"):
        return

    # 1. One item cannot have same customer multiple times
    seen_customers = set()
    for row in doc.customer_items:
        if not row.customer_name:
            continue
        if row.customer_name in seen_customers:
            frappe.throw(_("Customer '{0}' is appearing twice in the customer table").format(row.customer_name))
        seen_customers.add(row.customer_name)

    # 2. One customer cannot have same ref_code for multiple item
    for row in doc.customer_items:
        if not row.customer_name or not row.ref_code:
            continue
        
        # Exclude Reference Code (Buyer SKU) "0" from uniqueness validation
        if str(row.ref_code).strip() == "0":
            continue

        # Check if another Item has the same customer_name and ref_code
        filters = {
            "customer_name": row.customer_name,
            "ref_code": row.ref_code,
            "parent": ["!=", doc.name],
            "parenttype": "Item"
        }
        
        duplicate_item_customers = frappe.get_all(
            "Item Customer Detail",
            filters=filters,
            fields=["parent", "customer_name", "ref_code"]
        )
        
        if duplicate_item_customers:
            unique_items = list(set([d.parent for d in duplicate_item_customers]))
            items_list_html = "<ul>" + "".join([f"<li>{item}</li>" for item in unique_items]) + "</ul>"
            frappe.throw(
                _("Customer '{0}' already has the Reference Code '{1}' assigned to the following items:<br>{2}").format(
                    row.customer_name, row.ref_code, items_list_html
                )
            )

def validate_brand_item_uniqueness(doc):
    if not doc.brand or not doc.item_name:
        return

    # Check if another item exists with the same brand and item_name
    filters = {
        "item_name": doc.item_name,
        "brand": doc.brand,
        "name": ["!=", doc.name]
    }
    
    duplicate_item = frappe.db.get_value("Item", filters, "name")
    
    if duplicate_item:
        item_link = frappe.utils.get_link_to_form("Item", duplicate_item)
        frappe.throw(
            _("An item with the name '{0}' already exists for the brand '{1}'.<br>See existing item: {2}").format(doc.item_name, doc.brand, item_link),
            frappe.ValidationError
        )


def set_supplier_skus(doc):
    """
    Populate supplier_skus field with comma-separated SKU codes
    from Supplier Items child table
    """
    
    # Get all SKU codes from the supplier_items child table
    sku_codes = []
    
    if doc.supplier_items:
        for supplier_item in doc.supplier_items:
            # Check if supplier_sku exists and is not empty
            if supplier_item.supplier_part_no:
                sku_codes.append(supplier_item.supplier_part_no.strip())
    
    if sku_codes:
        # Join all SKU codes with comma and space
        supplier_skus_text = ", ".join(sku_codes) if sku_codes else ""
        
        # Set the custom field value
        doc.custom_supplier_skus = supplier_skus_text


# Checks added
# - Only digits allowed
# - Length must be 8 or 13
# - How this works:
#   - Starting from the rightmost digit, alternate between multiplying by 3 and 1
#   - Sum up all the results
#   - The last digit should be the result when 10 is subtracted from the sum
def validate_item_integrity(doc):
    if doc.item_group != 'Service Items' and not doc.has_variants and doc.is_stock_item:
        if not doc.get("custom_ean"):
            frappe.throw(_("EAN is mandatory"), frappe.MandatoryError)

def validate_ean(doc):
    if not frappe.db.get_single_value("Kindlife Settings", "enable_ean_validation"):
        return

    ean = doc.get("custom_ean")
    if not ean:
        return
        
    if not frappe.db.get_single_value("Kindlife Settings", "enable_ean_validation"):
        return

    # Only digits allowed
    if not ean.isdigit():
        frappe.throw(_("EAN must contain only numbers. Please remove spaces or special characters. To disable ean validation, deactivate it in Kindlife Settings."), frappe.ValidationError)

    # Length must be 8 or 13
    if len(ean) not in [8, 13]:
        frappe.throw(_("EAN must be exactly 8 or 13 characters long. To disable ean validation, deactivate it in Kindlife Settings."), frappe.ValidationError)

    # How this works:
    # The last digit should be the result when a certain logic is run on the remaining digits. The logic is as mentioned below:
    # - Starting from the rightmost digit, alternate between multiplying by 3 and 1
    # - Sum up all the results
    # - The last digit should be the result when 10 is subtracted from the sum
    digits = [int(d) for d in ean]
    data = digits[:-1]
    check_digit = digits[-1]

    total = 0
    for i, digit in enumerate(reversed(data)):
        if i % 2 == 0:
            total += digit * 3
        else:
            total += digit * 1

    calculated_check_digit = (10 - (total % 10)) % 10
    if calculated_check_digit != check_digit:
        frappe.throw(_("Invalid EAN. To disable ean validation, deactivate it in Kindlife Settings."), frappe.ValidationError)

# Calling this in on_update will ensure that the function is called only after all validations are run
def on_update(doc, method):
    
    """
        Add/Update item on CS_Cart
    """
    pass

    update_cs_cart(doc)




def update_cs_cart(item_doc):
    if not frappe.db.get_single_value("CS Cart Settings", "enable_item_syncing"):
        print("Item syncing is disabled")
        return
    print("Item syncing is enabled")
    try:
        if item_doc.supplier_items:  # Send topmost sku code
            # The supplier_items[0] always gives topmost item from the table (idx = 1) so we dont need to filter it here
            supplier_sku = item_doc.supplier_items[0].supplier_part_no
            supplier_name = item_doc.supplier_items[0].supplier
            cs_cart_supplier_id = frappe.db.get_value("Supplier", {"name": supplier_name}, "custom_supplier_id")
        else:
            supplier_sku = ""
            cs_cart_supplier_id = ""

        data = {
            "product": item_doc.item_name,
            "product_code": item_doc.custom_cs_cart_product_code,
            "supplier_id": cs_cart_supplier_id,
            "list_price": item_doc.custom_mrp or 0,
            "kl_erp_inventory_id": item_doc.name or '',
            "hsn_code": item_doc.gst_hsn_code or '',        # Fetched from gst_hsn_code field on Item (auto-fetched from Item Group)
            "item_group": item_doc.item_group or '',
            "custom_is_bundle_item": 1 if item_doc.get("custom_is_bundle_item") else 0,
            "is_stock_item": 1 if item_doc.is_stock_item else 0,
            "custom_ean": item_doc.custom_ean or '',
            "brand": item_doc.brand or '',
            "stock_uom": item_doc.stock_uom or '',
            "custom_fulfilled_by": item_doc.custom_fulfilled_by or '',
            "has_variants": item_doc.has_variants or '',
            "variant_of": item_doc.variant_of or '',        # Parent item code if this is a variant, else empty
            "cs_cart_product_code": item_doc.custom_cs_cart_product_code or '',
            "product_ids": item_doc.custom_b2c_product_id or '',  # Comma-separated; CS Cart updates all duplicates internally
        }

        # If this item is a Product Bundle, fetch child items and include them
        if item_doc.get("custom_is_bundle_item"):  # custom_is_bundle_item flag on Item doc
            product_bundle_items = []
            # Product Bundle doc name matches the parent item name
            bundle_doc = frappe.get_doc("Product Bundle", item_doc.name)
            for bundle_row in bundle_doc.items:
                child_item_doc = frappe.get_doc("Item", bundle_row.item_code)

                # Get supplier info for child item
                if child_item_doc.supplier_items:
                    child_supplier_name = child_item_doc.supplier_items[0].supplier
                    child_supplier_id = frappe.db.get_value("Supplier", {"name": child_supplier_name}, "custom_supplier_id") or ""
                else:
                    child_supplier_id = ""

                product_bundle_items.append({
                    "product": child_item_doc.item_name,
                    "product_code": child_item_doc.custom_cs_cart_product_code or '',
                    "supplier_id": child_supplier_id,
                    "qty": bundle_row.qty,
                    "list_price": child_item_doc.custom_mrp or 0,
                    "kl_erp_inventory_id": child_item_doc.name or '',
                    "hsn_code": child_item_doc.gst_hsn_code or '',
                    "item_group": child_item_doc.item_group or '',
                    "custom_is_bundle_item": 1 if child_item_doc.get("custom_is_bundle_item") else 0,
                    "is_stock_item": 1 if child_item_doc.is_stock_item else 0,
                    "custom_ean": child_item_doc.custom_ean or '',
                    "brand": child_item_doc.brand or '',
                    "stock_uom": child_item_doc.stock_uom or '',
                    "custom_fulfilled_by": child_item_doc.custom_fulfilled_by or '',
                    "variant_of": child_item_doc.variant_of or '',
                    "cs_cart_product_code": child_item_doc.custom_cs_cart_product_code or '',
                    "product_ids": child_item_doc.custom_b2c_product_id or '',
                })

            data["product_bundle_items"] = product_bundle_items

        api = CSCartAPI()

        # Single call — CS Cart handles updating all duplicate products on their end
        response = api.sync_product(data=data)
        print("response", response)

        # CS Cart returns product_id as a list [70364] or string "70364"; normalize to comma-separated and save back
        returned_product_ids = response.get("product_id", "")
        if returned_product_ids:
            if isinstance(returned_product_ids, list):
                returned_product_ids = ",".join(str(pid) for pid in returned_product_ids)
            else:
                returned_product_ids = str(returned_product_ids).strip()
            item_doc.db_set("custom_b2c_product_id", returned_product_ids)
            frappe.db.commit()

        frappe.msgprint("CS-Cart updated successfully")
    except Exception as e:
        frappe.log_error(f"CS-Cart API General Error", f"CS-Cart API Error {e}")
        frappe.msgprint(f"CS-Cart sync failed: {e}", title="CS-Cart Error", indicator="red")


def on_update_product_bundle(doc, method):
    """
    Called when a Product Bundle document is saved/updated.
    Loads the parent Item (same name as the bundle) and re-runs the CS Cart sync
    so that the updated bundle items list is pushed to CS Cart.
    """
    try:
        item_doc = frappe.get_doc("Item", doc.new_item_code)
        update_cs_cart(item_doc)
    except Exception as e:
        frappe.log_error(f"CS-Cart sync failed after Product Bundle update", f"CS-Cart API Error {e}")


def validate_prohibited_words(doc):
    if not doc.item_name:
        return

    # Fetch prohibited words from cache or DB
    def get_prohibited_words():
        prohibited_list = frappe.get_all("Prohibited Words", pluck="word", parent_doctype="Prohibited Words in Item Name")
        return {w.lower() for w in prohibited_list if w}

    prohibited_set = frappe.cache().get_value("prohibited_words_list", generator=get_prohibited_words)

    # Normalize item name
    # Split by non-alphanumeric characters
    tokens = re.split(r'[^a-zA-Z0-9]+', doc.item_name)
    
    found_words = []
    for token in tokens:
        if token.lower() in prohibited_set:
            found_words.append(token)
            
    if found_words:
        frappe.throw(
            _("Item Name contains prohibited words: {0}").format(", ".join(found_words)),
            frappe.ValidationError
        )
