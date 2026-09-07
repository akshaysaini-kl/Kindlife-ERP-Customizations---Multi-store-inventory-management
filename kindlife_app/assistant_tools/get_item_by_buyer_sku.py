import frappe
from frappe_assistant_core.core.base_tool import BaseTool

class GetItemByBuyerSku(BaseTool):
    def __init__(self):
        super().__init__()
        
        self.name = "get_item_by_buyer_sku"
        self.description = "Finds an Item using the Customer's SKU (Reference Code)."
        self.category = "Inventory"
        self.source_app = "kindlife_app"
        
        # Define strict JSON Schema
        self.inputSchema = {
            "type": "object",
            "properties": {
                "buyer_sku": {
                    "type": "string",
                    "description": "The SKU code used by the buyer/customer."
                },
                "customer": {
                    "type": "string",
                    "description": "Optional: Name of the customer to filter by."
                }
            },
            "required": ["buyer_sku"]
        }

    def execute(self, arguments):
        buyer_sku = arguments.get("buyer_sku")
        customer = arguments.get("customer")
        
        # Original Logic Construction
        filters = {"ref_code": buyer_sku}
        if customer:
            filters["customer_name"] = customer

        # 1. Find all matching internal Item Codes
        # We use get_all to retrieve a list of dictionaries, e.g. [{'parent': 'ITEM-001'}, {'parent': 'ITEM-002'}]
        results = frappe.db.get_all(
            "Item Customer Detail",
            filters=filters,
            fields=["parent", "customer_name", "ref_code"]
        )

        if not results:
            return {
                "status": "not_found",
                "message": f"No Items found for Buyer SKU {buyer_sku}" + (f" and customer {customer}" if customer else "")
            }

        found_items = []
        seen_items = set()
        
        for row in results:
            item_code = row.parent
            
            # Skip if we already found this item
            if item_code in seen_items:
                continue
                
            seen_items.add(item_code)

            # Fetch item details
            # We use get_value here for efficiency if we only need specific fields, 
            # or get_doc if we need the full object. Let's start with basic details.
            item_details = frappe.db.get_value(
                "Item", 
                item_code, 
                ["item_name", "stock_uom", "description"], 
                as_dict=True
            )
            
            if item_details:
                found_items.append({
                    "item_code": item_code,
                    "item_name": item_details.item_name,
                    "stock_uom": item_details.stock_uom,
                    "description": item_details.description,
                    "matched_customer": row.customer_name,
                    "matched_sku": row.ref_code
                })

        return {
            "status": "success",
            "count": len(found_items),
            "items": found_items
        }

