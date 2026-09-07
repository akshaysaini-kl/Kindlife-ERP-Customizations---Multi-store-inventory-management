import frappe
from frappe.utils import nowdate, nowtime, flt
from erpnext.stock.utils import get_stock_balance
from erpnext.stock.doctype.warehouse.warehouse import get_child_warehouses


@frappe.whitelist()
def get_item_warehouse_inventory(item_code, warehouse, posting_date=None, posting_time=None):
    """
    Get current stock balance for an item in a specific warehouse.
    If warehouse is a parent/group warehouse, it will sum up stock from all child warehouses.
    
    Args:
        item_code (str): Item Code
        warehouse (str): Warehouse name (can be parent or child warehouse)
        posting_date (str, optional): Date for stock balance. Defaults to current date.
        posting_time (str, optional): Time for stock balance. Defaults to current time.
    
    Returns:
        dict: Dictionary containing stock balance information
            - item_code: Item Code
            - warehouse: Warehouse name
            - is_group: Whether the warehouse is a group/parent warehouse
            - actual_qty: Current stock quantity (sum of all child warehouses if parent)
            - valuation_rate: Weighted average valuation rate
            - stock_value: Total stock value (qty * rate)
            - posting_date: Date of the balance
            - posting_time: Time of the balance
            - child_warehouses: List of child warehouse stock details (if parent warehouse)
    """
    # Validate inputs
    if not item_code:
        frappe.throw("Item Code is required")
    
    if not warehouse:
        frappe.throw("Warehouse is required")
    
    # Set default date and time if not provided
    if not posting_date:
        posting_date = nowdate()
    if not posting_time:
        posting_time = nowtime()
    
    # Get stock balance with valuation rate
    try:
        # Check if warehouse is a group/parent warehouse
        warehouse_info = frappe.db.get_value(
            "Warehouse",
            warehouse,
            ["warehouse_name", "is_group"],
            as_dict=True
        )
        
        if not warehouse_info:
            frappe.throw(f"Warehouse {warehouse} not found")
        
        is_group = warehouse_info.get("is_group", 0)
        
        # Get additional item details
        item_details = frappe.db.get_value(
            "Item",
            item_code,
            ["item_name", "stock_uom"],
            as_dict=True
        )
        
        if not item_details:
            frappe.throw(f"Item {item_code} not found")
        
        # If it's a group warehouse, get all child warehouses and sum their stock
        if is_group:
            child_warehouses_list = get_child_warehouses(warehouse)
            
            total_qty = 0.0
            total_value = 0.0
            child_warehouse_details = []
            
            for child_wh in child_warehouses_list:
                # Skip the parent warehouse itself in the loop
                if child_wh == warehouse:
                    continue
                
                # Check if this child is also a group (we only want leaf warehouses)
                child_is_group = frappe.db.get_value("Warehouse", child_wh, "is_group")
                if child_is_group:
                    continue
                
                child_qty, child_rate = get_stock_balance(
                    item_code=item_code,
                    warehouse=child_wh,
                    posting_date=posting_date,
                    posting_time=posting_time,
                    with_valuation_rate=True
                )
                
                child_value = flt(child_qty) * flt(child_rate)
                total_qty += flt(child_qty)
                total_value += child_value
                
                # Only include warehouses with stock in the details
                if flt(child_qty) != 0:
                    child_warehouse_details.append({
                        "warehouse": child_wh,
                        "actual_qty": flt(child_qty),
                        "valuation_rate": flt(child_rate),
                        "stock_value": child_value
                    })
            
            # Calculate weighted average rate
            avg_rate = (total_value / total_qty) if total_qty > 0 else 0.0
            
            return {
                "item_code": item_code,
                "item_name": item_details.get("item_name"),
                "warehouse": warehouse,
                "warehouse_name": warehouse_info.get("warehouse_name"),
                "is_group": 1,
                "actual_qty": flt(total_qty),
                "stock_uom": item_details.get("stock_uom"),
                "valuation_rate": flt(avg_rate),
                "stock_value": flt(total_value),
                "posting_date": posting_date,
                "posting_time": posting_time,
                "child_warehouses": child_warehouse_details
            }
        else:
            # Single warehouse - get stock balance directly
            qty, rate = get_stock_balance(
                item_code=item_code,
                warehouse=warehouse,
                posting_date=posting_date,
                posting_time=posting_time,
                with_valuation_rate=True
            )
            
            # Calculate stock value
            stock_value = flt(qty) * flt(rate)
            
            return {
                "item_code": item_code,
                "item_name": item_details.get("item_name"),
                "warehouse": warehouse,
                "warehouse_name": warehouse_info.get("warehouse_name"),
                "is_group": 0,
                "actual_qty": flt(qty),
                "stock_uom": item_details.get("stock_uom"),
                "valuation_rate": flt(rate),
                "stock_value": flt(stock_value),
                "posting_date": posting_date,
                "posting_time": posting_time
            }
    
    except Exception as e:
        frappe.log_error(f"Error getting stock balance for {item_code} in {warehouse}: {str(e)}")
        frappe.throw(f"Error getting stock balance: {str(e)}")
