# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

"""
Inventory Sync Module for CS Cart Integration

This module handles real-time inventory synchronization from ERPNext to CS Cart.
It is triggered by Stock Ledger Entry submissions and pushes consolidated inventory
data including good quantity, bad quantity, and open order quantity.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate
from erpnext.stock.utils import get_stock_balance
from erpnext.stock.doctype.warehouse.warehouse import get_child_warehouses
from kindlife_app.services.cscart_service import CSCartAPI
import traceback


def create_sync_log(item_code):
    """Create a new sync log entry"""
    try:
        log = frappe.get_doc({
            "doctype": "CS Cart Sync Log",
            "item_code": item_code,
            "status": "Queued",
            "message": "Enqueued for sync..."
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit() # Commit to ensure ID is generated
        return log.name
    except Exception as e:
        frappe.log_error(f"Failed to create sync log: {str(e)}", "CS Cart Sync Log Creation Error")
        return None

def on_stock_ledger_entry_submit(doc, method=None):
    """
    Hook function triggered after Stock Ledger Entry submission.
    This captures all inventory changes in ERPNext.
    
    Enqueues the sync job to run in background to avoid blocking stock transactions.
    """
    try:
        # Check if inventory sync is enabled
        if not is_inventory_sync_enabled():
            return
        
        # Get the item code from the stock ledger entry
        item_code = doc.item_code
        
        # Check if this item should be synced
        if not should_sync_item(item_code):
            return
            
        # Create Log Entry
        log_name = create_sync_log(item_code)
        
        # Enqueue the sync job to run in background
        frappe.enqueue(
            method="kindlife_app.custom_scripts.inventory_sync.sync_inventory_to_cscart",
            queue="default",  # Use 'default' queue for normal priority
            timeout=300,  # 5 minute timeout
            is_async=True,  # Run asynchronously
            job_name=f"cs_cart_inventory_sync_{item_code}",  # Unique job name
            item_code=item_code,  # Pass item_code as argument
            log_name=log_name, # Pass log_name
            enqueue_after_commit=True  # Wait for transaction commit before enqueuing
        )
        
        frappe.logger().info(f"Enqueued inventory sync for item {item_code} (Log: {log_name})")

        # Also sync any Product Bundles that contain this component
        enqueue_bundle_syncs_for_item(item_code)
        
    except Exception as e:
        # Log error but don't block the stock transaction
        frappe.log_error(
            message=f"Failed to enqueue inventory sync for item {doc.item_code}: {str(e)}\n{traceback.format_exc()}",
            title=f"CS Cart Inventory Sync - Enqueue Failed - {doc.item_code}"
        )


def on_pick_list_change(doc, method=None):
    """
    Hook triggered when a Pick List is created (after_insert) or cancelled (on_cancel).

    Returns immediately — offloads all work to a background dispatcher so the
    Pick List API is never slowed down.
    """
    try:
        frappe.enqueue(
            method="kindlife_app.custom_scripts.inventory_sync.dispatch_pick_list_inventory_sync",
            queue="default",
            timeout=300,
            is_async=True,
            job_name=f"cs_cart_pl_dispatch_{doc.name}",
            pick_list_name=doc.name,
            enqueue_after_commit=True
        )
    except Exception as e:
        frappe.log_error(
            message=f"Failed to enqueue Pick List sync dispatcher for {doc.name}: {str(e)}\n{traceback.format_exc()}",
            title=f"CS Cart Inventory Sync - Pick List Dispatch Failed - {doc.name}"
        )


def dispatch_pick_list_inventory_sync(pick_list_name):
    """
    Background dispatcher: reads the Pick List, finds unique B2C item codes,
    and enqueues one sync job per item.

    Runs entirely in the worker — the request thread is never blocked.
    """
    try:
        if not is_inventory_sync_enabled():
            return

        # Load item codes directly from the child table (no need to load full doc)
        rows = frappe.db.get_all(
            "Pick List Item",
            filters={"parent": pick_list_name},
            pluck="item_code"
        )
        item_codes = list(set(rows))

        for item_code in item_codes:
            if not should_sync_item(item_code):
                continue

            log_name = create_sync_log(item_code)

            frappe.enqueue(
                method="kindlife_app.custom_scripts.inventory_sync.sync_inventory_to_cscart",
                queue="default",
                timeout=300,
                is_async=True,
                job_name=f"cs_cart_inventory_sync_{item_code}",
                item_code=item_code,
                log_name=log_name,
                enqueue_after_commit=True
            )

            frappe.logger().info(
                f"Enqueued inventory sync for item {item_code} "
                f"via Pick List {pick_list_name} dispatcher (Log: {log_name})"
            )

            # Also sync any Product Bundles that contain this component
            enqueue_bundle_syncs_for_item(item_code)

    except Exception as e:
        frappe.log_error(
            message=f"Pick List sync dispatcher failed for {pick_list_name}: {str(e)}\n{traceback.format_exc()}",
            title=f"CS Cart Inventory Sync - Dispatcher Failed - {pick_list_name}"
        )



def is_inventory_sync_enabled():
    """
    Check if inventory sync is enabled in CS Cart Settings.
    
    Returns:
        bool: True if sync is enabled, False otherwise
    """
    try:
        settings = frappe.get_single("CS Cart Settings")
        return settings.get("enable_inventory_sync", 0) == 1
    except Exception as e:
        frappe.log_error(
            message=f"Error checking inventory sync settings: {str(e)}",
            title="CS Cart Inventory Sync - Settings Error"
        )
        return False


def update_last_sync_time():
    """
    Update the last inventory sync timestamp in CS Cart Settings.
    """
    try:
        settings = frappe.get_single("CS Cart Settings")
        settings.last_inventory_sync = frappe.utils.now_datetime()
        settings.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            message=f"Error updating last sync time: {str(e)}",
            title="CS Cart Inventory Sync - Update Time Error"
        )


def should_sync_item(item_code):
    """
    Check if an item should be synced to CS Cart.
    
    Args:
        item_code: Item Code to check
    
    Returns:
        bool: True if item should be synced, False otherwise
    """
    try:
        # Get item details
        item = frappe.get_cached_doc("Item", item_code)
        
        
        # Item must have a product code (supplier SKU)
        if not item.supplier_items or len(item.supplier_items) == 0:
            frappe.log_error(
                message=f"Item {item_code} is B2C but has no supplier SKU. Skipping inventory sync.",
                title=f"CS Cart Inventory Sync - Missing Product Code"
            )
            return False
        
        return True
        
    except Exception as e:
        frappe.log_error(
            message=f"Error checking if item {item_code} should sync: {str(e)}",
            title="CS Cart Inventory Sync - Item Check Error"
        )
        return False


def get_main_warehouse():
    """
    Get all main warehouses (marked with custom_main_warehouse = 1).

    There can be more than one main warehouse group (e.g. one per fulfilment
    centre).  The function returns a list so that callers can iterate over
    every warehouse and aggregate inventory accordingly.

    Returns:
        list: Main warehouse names; empty list if none found
    """
    try:
        main_warehouses = frappe.db.get_all(
            "Warehouse",
            filters={"custom_main_warehouse": 1, "is_group": 1},
            pluck="name"
        )

        if not main_warehouses:
            frappe.log_error(
                message="No main warehouse found with custom_main_warehouse = 1",
                title="CS Cart Inventory Sync - Main Warehouse Not Found"
            )

        return main_warehouses or []

    except Exception as e:
        frappe.log_error(
            message=f"Error getting main warehouse: {str(e)}",
            title="CS Cart Inventory Sync - Main Warehouse Error"
        )
        return []


def get_rejected_warehouses(main_warehouse):
    """
    Get all rejected warehouses under the main warehouse.
    
    Args:
        main_warehouse: Main warehouse name
    
    Returns:
        list: List of rejected warehouse names
    """
    try:
        # Get all child warehouses
        child_warehouses = get_child_warehouses(main_warehouse)
        
        # Filter for rejected warehouses
        rejected_warehouses = frappe.db.get_all(
            "Warehouse",
            filters={
                "name": ["in", child_warehouses],
                "is_rejected_warehouse": 1
            },
            pluck="name"
        )
        
        return rejected_warehouses or []
        
    except Exception as e:
        frappe.log_error(
            message=f"Error getting rejected warehouses: {str(e)}",
            title="CS Cart Inventory Sync - Rejected Warehouse Error"
        )
        return []


def calculate_open_order_quantity(item_code, warehouse):
    """
    Calculate quantity reserved in active pick lists for an item.

    Uses Pick List Items (not Sales Order pending qty) because pick lists
    represent actual physical stock reservation with warehouse and batch-level
    granularity. ERPNext prevents the same stock from being allocated to two
    pick lists, so this accurately reflects what is truly unavailable.

    Mirrors ERPNext's internal _get_pick_list_items() logic:
      - For submitted pick list items: picked_qty - delivered_qty
      - For draft pick list items: stock_qty
    Only considers pick lists that are NOT Completed or Cancelled.

    Args:
        item_code: Item Code
        warehouse: Warehouse name (can be group warehouse)

    Returns:
        float: Total quantity reserved in active pick lists
    """
    try:
        # Get all child warehouses if it's a group warehouse
        warehouses = [warehouse]
        is_group = frappe.db.get_value("Warehouse", warehouse, "is_group")

        if is_group:
            warehouses = get_child_warehouses(warehouse)

        if not warehouses:
            return 0.0

        # Query active pick list items — mirrors pick_list.py _get_pick_list_items()
        result = frappe.db.sql("""
            SELECT
                SUM(
                    CASE
                        WHEN (pli.picked_qty > 0 AND pli.docstatus = 1)
                        THEN pli.picked_qty - IFNULL(pli.delivered_qty, 0)
                        ELSE pli.stock_qty
                    END
                ) AS reserved_qty
            FROM `tabPick List Item` pli
            INNER JOIN `tabPick List` pl ON pl.name = pli.parent
            WHERE pli.item_code = %(item_code)s
                AND pli.warehouse IN %(warehouses)s
                AND pl.status NOT IN ('Completed', 'Cancelled')
                AND pli.docstatus != 2
                AND (pli.picked_qty > 0 OR pli.stock_qty > 0)
        """, {
            "item_code": item_code,
            "warehouses": warehouses
        }, as_dict=True)

        return flt(result[0].reserved_qty) if result else 0.0

    except Exception as e:
        frappe.log_error(
            message=f"Error calculating pick list reserved quantity for {item_code}: {str(e)}",
            title="CS Cart Inventory Sync - Pick List Qty Error"
        )
        return 0.0


def get_consolidated_inventory(item_code, main_warehouse):
    """
    Get consolidated inventory data for an item.

    Works with both group (parent) and leaf (child) warehouses:
    - Group warehouse: aggregates all child warehouses, separating good vs rejected.
    - Leaf warehouse: uses the warehouse directly; classified as good or bad
      based on its own ``is_rejected_warehouse`` flag.

    Args:
        item_code: Item Code
        main_warehouse: Warehouse name (group or leaf)

    Returns:
        dict: Consolidated inventory data with GoodQuantity, BadQuantity,
              openOrderQuantity, or None on error.
    """
    try:
        is_group = frappe.db.get_value("Warehouse", main_warehouse, "is_group")

        if is_group:
            # --- Group warehouse: traverse the full hierarchy ---
            child_warehouses = get_child_warehouses(main_warehouse)
            rejected_warehouses = get_rejected_warehouses(main_warehouse)

            # Good quantity: leaf children that are not rejected or QC
            qc_warehouses = frappe.db.get_all(
                "Warehouse",
                filters={"name": ["in", child_warehouses], "custom_is_qc_warehouse": 1},
                pluck="name"
            ) or []
            
            good_qty = 0.0
            for warehouse in child_warehouses:
                if warehouse == main_warehouse or warehouse in rejected_warehouses or warehouse in qc_warehouses:
                    continue
                if frappe.db.get_value("Warehouse", warehouse, "is_group"):
                    continue
                good_qty += flt(get_stock_balance(
                    item_code=item_code,
                    warehouse=warehouse,
                    posting_date=nowdate()
                ))

            # Bad quantity: rejected leaf children
            bad_qty = 0.0
            for warehouse in rejected_warehouses:
                if frappe.db.get_value("Warehouse", warehouse, "is_group"):
                    continue
                qty, _ = get_stock_balance(
                    item_code=item_code,
                    warehouse=warehouse,
                    posting_date=nowdate(),
                    with_valuation_rate=True
                )
                bad_qty += flt(qty)

        else:
            # --- Leaf warehouse: classify by its own rejected flag ---
            is_rejected = frappe.db.get_value("Warehouse", main_warehouse, "is_rejected_warehouse")
            is_qc = frappe.db.get_value("Warehouse", main_warehouse, "custom_is_qc_warehouse")

            balance = flt(get_stock_balance(
                item_code=item_code,
                warehouse=main_warehouse,
                posting_date=nowdate()
            ))

            if is_rejected:
                good_qty = 0.0
                bad_qty = balance
            elif is_qc:
                good_qty = 0.0
                bad_qty = 0.0
            else:
                good_qty = balance
                bad_qty = 0.0

        # Calculate pick list reserved quantity (stock allocated to active pick lists)
        open_order_qty = calculate_open_order_quantity(item_code, main_warehouse)

        return {
            "Warehouse": main_warehouse,
            "GoodQuantity": good_qty,
            "BadQuantity": bad_qty,
            "openOrderQuantity": open_order_qty
        }

    except Exception as e:
        frappe.log_error(
            message=f"Error getting consolidated inventory for {item_code}: {str(e)}\n{traceback.format_exc()}",
            title="CS Cart Inventory Sync - Consolidated Inventory Error"
        )
        return None


# ---------------------------------------------------------------------------
# Product Bundle helpers
# ---------------------------------------------------------------------------

def get_bundles_containing_item(item_code):
    """
    Return the list of Product Bundle parent item codes that have
    ``item_code`` as a component.

    ERPNext stores bundle components in the ``Product Bundle Item`` child
    table. The ``parent`` field on that table is the Product Bundle name,
    which is the same as its parent item code (``new_item_code``).

    Args:
        item_code: Component item code to look up

    Returns:
        list: Distinct bundle parent item codes
    """
    try:
        bundle_names = frappe.db.get_all(
            "Product Bundle Item",
            filters={"item_code": item_code},
            pluck="parent"  # parent == Product Bundle name == bundle's new_item_code
        )
        return list(set(bundle_names))
    except Exception as e:
        frappe.log_error(
            message=f"Error fetching bundles containing {item_code}: {str(e)}",
            title="CS Cart Inventory Sync - Bundle Lookup Error"
        )
        return []


def get_bundle_inventory(bundle_item_code, main_warehouse):
    """
    Calculate virtual inventory for a Product Bundle parent item.

    A Product Bundle carries no physical stock. Its available quantity is
    derived from its components:

        bundle_qty = floor( min( component_stock / component_qty_in_bundle ) )

    This is computed **independently** for GoodQuantity, BadQuantity, and
    openOrderQuantity so that each dimension is bottlenecked by its own
    weakest component.

    Args:
        bundle_item_code: Product Bundle parent item code (new_item_code)
        main_warehouse: Main warehouse name (group or leaf)

    Returns:
        dict: Same shape as get_consolidated_inventory() — keys Warehouse,
              GoodQuantity, BadQuantity, openOrderQuantity — or None on error.
    """
    try:
        bundle = frappe.get_cached_doc("Product Bundle", bundle_item_code)

        if not bundle.items:
            frappe.log_error(
                message=f"Product Bundle {bundle_item_code} has no items.",
                title="CS Cart Inventory Sync - Empty Bundle"
            )
            return None

        min_good = float("inf")
        min_bad  = float("inf")
        min_open = float("inf")

        for row in bundle.items:
            comp_inv = get_consolidated_inventory(row.item_code, main_warehouse)
            if comp_inv is None:
                # Can't compute the bundle if any component fails
                return None

            qty = flt(row.qty) or 1  # qty of component per bundle unit

            # floor division — you can only make whole bundles
            min_good = min(min_good, flt(comp_inv["GoodQuantity"])   // qty)
            min_bad  = min(min_bad,  flt(comp_inv["BadQuantity"])    // qty)
            min_open = min(min_open, flt(comp_inv["openOrderQuantity"]) // qty)

        return {
            "Warehouse": main_warehouse,
            "GoodQuantity":      max(0.0, min_good if min_good != float("inf") else 0.0),
            "BadQuantity":       max(0.0, min_bad  if min_bad  != float("inf") else 0.0),
            "openOrderQuantity": max(0.0, min_open if min_open != float("inf") else 0.0),
        }

    except Exception as e:
        frappe.log_error(
            message=f"Error calculating bundle inventory for {bundle_item_code}: {str(e)}\n{traceback.format_exc()}",
            title="CS Cart Inventory Sync - Bundle Inventory Error"
        )
        return None


def sync_bundle_inventory_to_cscart(bundle_item_code, log_name=None):
    """
    Sync virtual inventory for a Product Bundle parent item to CS Cart.

    Mirrors sync_inventory_to_cscart() but uses get_bundle_inventory()
    to derive the bundle qty from its components.

    Args:
        bundle_item_code: Product Bundle parent item code
        log_name: Optional CS Cart Sync Log name to update

    Returns:
        dict: Sync result with keys ``status`` and ``message``
    """
    log_doc = None
    if log_name:
        try:
            log_doc = frappe.get_doc("CS Cart Sync Log", log_name)
            log_doc.status = "Processing"
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            pass

    try:
        main_warehouses = get_main_warehouse()
        if not main_warehouses:
            raise Exception("No main warehouse configured (custom_main_warehouse = 1)")

        # The bundle parent item must carry a supplier_part_no (CS Cart product code)
        item = frappe.get_cached_doc("Item", bundle_item_code)
        product_code = None
        if item.supplier_items and len(item.supplier_items) > 0:
            product_code = item.supplier_items[0].supplier_part_no

        if not product_code:
            raise Exception(f"No product code found for bundle item {bundle_item_code}")

        if log_doc:
            log_doc.product_code = product_code

        # Build one consolidatedInventory entry per main warehouse
        bundle_inventory_list = []
        for main_warehouse in main_warehouses:
            inv = get_bundle_inventory(bundle_item_code, main_warehouse)
            if inv is None:
                raise Exception(f"Failed to calculate bundle inventory for warehouse {main_warehouse}")
            bundle_inventory_list.append(inv)

        inventory_data = [{
            "item_code":   bundle_item_code,
            "product_code": product_code,
            "success": True,
            "message": "success",
            "consolidatedInventory": bundle_inventory_list
        }]

        if log_doc:
            log_doc.request_data = frappe.as_json(inventory_data)
            log_doc.save(ignore_permissions=True)

        api = CSCartAPI()
        response = api.push_inventory_update(inventory_data)

        update_last_sync_time()

        if log_doc:
            log_doc.status = "Success"
            log_doc.response_data = frappe.as_json(response)
            log_doc.message = "Bundle sync successful"
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()

        frappe.logger().info(
            f"Bundle inventory synced successfully for {bundle_item_code}: {response}"
        )
        return {"status": "success", "message": "Bundle inventory synced successfully", "response": response}

    except Exception as e:
        error_msg = f"Failed to sync bundle inventory for {bundle_item_code}: {str(e)}"
        detailed_error = f"{str(e)}\n{traceback.format_exc()}"

        if log_doc:
            log_doc.status = "Failed"
            log_doc.message = str(e)[:140]
            log_doc.response_data = detailed_error
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()

        frappe.log_error(
            message=detailed_error,
            title=f"CS Cart Bundle Inventory Sync Failed - {bundle_item_code}"
        )
        return {"status": "error", "message": str(e)}


def enqueue_bundle_syncs_for_item(item_code):
    """
    Find all Product Bundles that contain ``item_code`` as a component
    and enqueue a bundle inventory sync job for each eligible bundle.

    A bundle is eligible if its parent item passes should_sync_item()
    (i.e. B2C + has a supplier_part_no).

    Args:
        item_code: Component item code whose stock just changed
    """
    try:
        bundle_codes = get_bundles_containing_item(item_code)
        if not bundle_codes:
            return

        for bundle_code in bundle_codes:
            if not should_sync_item(bundle_code):
                frappe.logger().debug(
                    f"Skipping bundle {bundle_code} — not eligible for sync."
                )
                continue

            log_name = create_sync_log(bundle_code)

            frappe.enqueue(
                method="kindlife_app.custom_scripts.inventory_sync.sync_bundle_inventory_to_cscart",
                queue="default",
                timeout=300,
                is_async=True,
                job_name=f"cs_cart_bundle_sync_{bundle_code}",
                bundle_item_code=bundle_code,
                log_name=log_name,
                enqueue_after_commit=True
            )

            frappe.logger().info(
                f"Enqueued bundle inventory sync for {bundle_code} "
                f"(triggered by component {item_code}, Log: {log_name})"
            )

    except Exception as e:
        frappe.log_error(
            message=f"enqueue_bundle_syncs_for_item failed for component {item_code}: {str(e)}\n{traceback.format_exc()}",
            title="CS Cart Inventory Sync - Bundle Enqueue Error"
        )


def sync_inventory_to_cscart(item_code, log_name=None):
    """
    Main function to sync inventory for a specific item to CS Cart.
    
    Args:
        item_code: Item Code to sync
        log_name: Optional existing Log DocType name to update
    
    Returns:
        dict: Sync result
    """
    log_doc = None
    if log_name:
        try:
            log_doc = frappe.get_doc("CS Cart Sync Log", log_name)
            log_doc.status = "Processing"
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            # If log retrieval fails, just log normally
            pass

    try:
        # Get all main warehouses
        main_warehouses = get_main_warehouse()
        if not main_warehouses:
            raise Exception("No main warehouse configured (custom_main_warehouse = 1)")

        # Get item details
        item = frappe.get_cached_doc("Item", item_code)
        
        # Get product code (supplier SKU)
        product_code = None
        if item.supplier_items and len(item.supplier_items) > 0:
            product_code = item.supplier_items[0].supplier_part_no
        
        if not product_code:
            raise Exception(f"No product code found for item {item_code}")
        
        if log_doc:
            log_doc.product_code = product_code

        # Build one consolidatedInventory entry per main warehouse
        consolidated_inventory_list = []
        for main_warehouse in main_warehouses:
            inv = get_consolidated_inventory(item_code, main_warehouse)
            if inv is None:
                raise Exception(f"Failed to get consolidated inventory for warehouse {main_warehouse}")
            consolidated_inventory_list.append(inv)

        # Prepare payload
        inventory_data = [{
            "item_code": item_code,
            "product_code": product_code,
            "success": True,
            "message": "success",
            "consolidatedInventory": consolidated_inventory_list
        }]
        
        if log_doc:
            log_doc.request_data = frappe.as_json(inventory_data)
            log_doc.save(ignore_permissions=True)
        
        # Push to CS Cart
        api = CSCartAPI()
        response = api.push_inventory_update(inventory_data)
        
        # Update last sync time on success
        update_last_sync_time()
        
        if log_doc:
            log_doc.status = "Success"
            log_doc.response_data = frappe.as_json(response)
            log_doc.message = "Sync successful"
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
        
        frappe.logger().info(f"Inventory synced successfully for {item_code}: {response}")
        
        return {
            "status": "success",
            "message": "Inventory synced successfully",
            "response": response
        }
        
    except Exception as e:
        error_msg = f"Failed to sync inventory for {item_code}: {str(e)}"
        detailed_error = f"{str(e)}\n{traceback.format_exc()}"
        
        if log_doc:
            log_doc.status = "Failed"
            log_doc.message = str(e)[:140] # Truncate for small text field
            log_doc.response_data = detailed_error # Store full trace in response/details
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
            
        frappe.log_error(
            message=detailed_error,
            title=f"CS Cart Inventory Sync Failed - {item_code}"
        )
        
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def manual_sync_inventory(item_code):
    """
    Manual API endpoint to trigger inventory sync for testing.
    
    Args:
        item_code: Item Code to sync
    
    Returns:
        dict: Sync result
    """
    if not should_sync_item(item_code):
        return {
            "status": "error",
            "message": f"Item {item_code} should not be synced (not B2C or missing product code)"
        }
    
    return sync_inventory_to_cscart(item_code)


@frappe.whitelist()
def manual_sync_bundle_inventory(bundle_item_code):
    """
    Manual API endpoint to trigger bundle inventory sync for testing.

    Validates that the bundle parent item is B2C and has a product code,
    then calls sync_bundle_inventory_to_cscart() synchronously so the
    caller gets an immediate response.

    Args:
        bundle_item_code: Product Bundle parent item code (new_item_code)

    Returns:
        dict: Sync result with keys ``status``, ``message``, and ``response``
    """
    if not should_sync_item(bundle_item_code):
        return {
            "status": "error",
            "message": (
                f"Bundle item {bundle_item_code} is not eligible for sync "
                "(not B2C or missing supplier product code)"
            )
        }

    # Verify it actually is a Product Bundle
    if not frappe.db.exists("Product Bundle", bundle_item_code):
        return {
            "status": "error",
            "message": f"No Product Bundle found with parent item code {bundle_item_code}"
        }

    return sync_bundle_inventory_to_cscart(bundle_item_code)
