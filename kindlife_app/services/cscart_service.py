import requests
import frappe
from frappe.utils.password import get_decrypted_password
import traceback


CS_CART_CONSTANTS = {
    "CS_CART_COMPANY_ID" : 13,
    "ITEM_STATUS" : "A",
    "CUSTOMER_NAME": "Roadskye Tradecom Pvt. Ltd.",
    "CUSTOMER_PRICE_LIST":"Roadsky Price List"
}

class CSCartAPI:
    def __init__(self):
        """
        Initialize CS-Cart API client with base URL and credentials.
        You can store credentials in Frappe Site Config or a Single Doctype.
        Example: frappe.get_site_config()["cscart"]["api_key"]
        """
        self.base_url = frappe.get_site_config().get("cscart_base_url")
        self.api_key = get_decrypted_password("CS Cart Settings", "CS Cart Settings", "api_token", raise_exception=False)

        if not self.base_url :
            frappe.log_error("CS-Cart API URL missing. Please set it in site-config.")
            frappe.msgprint("CS-Cart API URL missing. Please set it in site-config.")
        if not self.api_key:
            frappe.log_error("CS-Cart API key missing. Please set it in CS Cart Settings.")
            frappe.msgprint("CS-Cart API key missing. Please set it in CS Cart Settings.")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }


    def request(self, endpoint, method="GET", data=None, params=None, product_id=None, include_defaults=True):
        """ Generic request handler for CS-Cart APIs """
        headers = self.headers.copy()
        if product_id:
            url = f"{self.base_url}/api/{endpoint}/{product_id}"
            headers.pop("Content-Type", None)
        else:
            url = f"{self.base_url}/api/{endpoint}"

        if include_defaults:
            defaults = {
                "status": CS_CART_CONSTANTS.get("ITEM_STATUS"),
                "company_id": CS_CART_CONSTANTS.get("CS_CART_COMPANY_ID")
            }
            data = {**data, **defaults}  # Adds values for status and company_id to data
        print(data)
        print(url)
        print(method)
        print(headers)  
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30
            )
            response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
            try:
                result = response.json()
            except Exception:
                # CS Cart sometimes prepends PHP debug output before the JSON body.
                # Try to extract the last valid JSON object from the raw text.
                import re, json as _json
                raw = response.text
                matches = re.findall(r'\{.*\}', raw, re.DOTALL)
                if matches:
                    try:
                        result = _json.loads(matches[-1])  # Parse the last {...} block
                    except Exception:
                        result = None
                else:
                    result = None
                if result is None:
                    # Truly unparseable — log and surface the raw text
                    frappe.log_error(f"CS-Cart API JSON Decode Error:\nURL:{url},\nMethod: {method},\nData Sent:{data},\nRaw Response: {raw}", "CS-Cart API Error")
                    raise Exception(f"CS-Cart returned non-JSON response: {raw}")

            # CS Cart sometimes returns HTTP 200 but embeds an error status in the body
            app_status = result.get("status") if isinstance(result, dict) else None
            if app_status and int(app_status) >= 400:
                # Extract all human-readable error messages from the errors dict
                errors = result.get("errors", {})
                messages = [v.get("message", "") for v in errors.values() if isinstance(v, dict)]
                error_detail = "; ".join(messages) if messages else result.get("message", str(result))
                frappe.log_error(f"CS-Cart API Application Error:\nURL:{url},\nStatus:{app_status},\nResponse:{result}", "CS-Cart API Error")
                raise Exception(f"CS-Cart Error ({app_status}): {error_detail}")

            return result
        except requests.exceptions.HTTPError as e:
            content = self.get_response_content(response)
            frappe.log_error(f"CS-Cart API HTTP Error:\nURL:{url},\nMethod: {method},\nData Sent:{data},\nResponse: {content},\nException: {traceback.format_exc()}", "CS-Cart API Error")
            # Raise with actual CS Cart error body so it shows correctly in the caller's msgprint
            raise Exception(f"CS-Cart returned {response.status_code}: {content}")
        except Exception as e:
            frappe.log_error(f"CS-Cart API General Error:\nURL:{url},\nMethod: {method},\nData Sent:{data},\nException: {traceback.format_exc()}", "CS-Cart API Error")
            raise

    def get_response_content(self, response):
        try:
            return response.json()
        except Exception:
            return response.text  # Fall back to raw text instead of the Response object


    def send_stock_info(self, stock_data):
        """
        Send stock information
        stock_data = {"product_id": 123, "stock": 50}
        """
        return self.request("send_stock_info", method="POST", data=stock_data)

    def get_orders(self, filters=None):
        """
        Example method to fetch orders
        filters = {"status": "open"}
        """
        return self.request("orders", method="GET", params=filters)

    def update_order_status(self, order_id, status):
        """
        Update order status
        """
        data = {"order_id": order_id, "status": status}
        return self.request("update-order-status", method="POST", data=data)

    def sync_product(self, data, product_id=None):
        if product_id:
            # Product exists on cs_cart, just update it
            return self.request("KlProductSyncErpHook", method="PUT", data=data, product_id=product_id, include_defaults=False)
        else:
            # Make new product
            return self.request("KlProductSyncErpHook", method="POST", data=data, include_defaults=False)

    def push_inventory_update(self, inventory_data):
        """
        Push inventory updates to CS Cart
        
        Args:
            inventory_data: List of inventory items with consolidated data
                [
                    {
                        "item_code": "MPL100008",
                        "product_code": "A1234",
                        "success": true,
                        "message": "success",
                        "consolidatedInventory": [
                            {
                                "Warehouse": "Edgistify - Dwarka - DPL",
                                "GoodQuantity": 1000,
                                "BadQuantity": 200,
                                "openOrderQuantity": 5
                            }
                        ]
                    }
                ]
        
        Returns:
            API response from CS Cart
        """
        if not inventory_data:
            return {"status": "error", "message": "No inventory data provided"}
        
        # Use a different request method for inventory updates
        # This endpoint doesn't need the default status and company_id
        url = f"{self.base_url}/api/KLErpInventoryUpdateHook"
        
        try:
            response = requests.request(
                method="POST",
                url=url,
                headers=self.headers,
                json=inventory_data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            content = self.get_response_content(response)
            frappe.log_error(
                f"CS-Cart Inventory Sync HTTP Error:\nURL:{url},\nData Sent:{inventory_data},\nResponse: {content},\nException: {traceback.format_exc()}", 
                "CS-Cart Inventory Sync Error"
            )
            raise
        except Exception as e:
            content = self.get_response_content(response)
            frappe.log_error(
                f"CS-Cart Inventory Sync General Error:\nURL:{url},\nData Sent:{inventory_data},\nResponse: {content},\nException: {traceback.format_exc()}", 
                "CS-Cart Inventory Sync Error"
            )
            raise