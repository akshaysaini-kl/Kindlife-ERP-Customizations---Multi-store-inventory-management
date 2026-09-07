import frappe


@frappe.whitelist()
def get_customer_via_address(gstin=None, city=None, state=None, pincode=None):
    """
    Get customer details via address based on GSTIN and city.
    
    Args:
        gstin (str): GST Identification Number
        city (str): City name
        state (str, optional): State name
        pincode (str, optional): PIN code
    
    Returns:
        dict: Response containing address ID, customer details, and price list
    """
    try:
        # Build filters dynamically based on what is provided
        filters = {}
        if gstin:
            filters["gstin"] = gstin
        if city:
            filters["city"] = city
        if state:
            filters["state"] = state
        if pincode:
            filters["pincode"] = pincode
        
        # Get matching addresses (or all if no filters provided)
        addresses = frappe.get_all(
            "Address",
            filters=filters,
            fields=["name", "address_line1", "address_line2", "city", "state", "pincode", "gstin","address_type"],
            order_by="creation ASC"
        )
        
        # Case 1: No results found
        if not addresses:
            frappe.response.http_status_code = 404
            msg = "No addresses found in the system"
            if filters:
                filter_str = ", ".join([f"{k}='{v}'" for k, v in filters.items()])
                msg = f"No address found matching filters: {filter_str}"
            return {
                "status": "error",
                "message": msg
            }
        
        # Case 2: Result(s) found - use first one for customer info, return all addresses
        selected_address = addresses[0]
        customer_info = get_customer_from_address(selected_address.name)
        
        return {
            "status": "success",
            "address_details": addresses,
            "customer": customer_info.get("customer")
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Customer via Address API Error")
        frappe.response.http_status_code = 500
        return {
            "status": "error",
            "message": str(e)
        }


def get_customer_from_address(address_name):
    """
    Get customer information linked to an address via Dynamic Link
    
    Args:
        address_name (str): Name of the address document
    
    Returns:
        dict: Complete customer object
    """
    try:
        # Get customer linked to this address via Dynamic Link
        customer_link = frappe.db.get_value(
            "Dynamic Link",
            {
                "parent": address_name,
                "parenttype": "Address",
                "link_doctype": "Customer"
            },
            "link_name"
        )
        
        if not customer_link:
            return {
                "customer": None
            }
        
        # Get complete customer document
        customer = frappe.get_cached_doc("Customer", customer_link)
        
        return {
            "customer": customer.as_dict()
        }
    
    except Exception as e:
        frappe.log_error(
            message=f"Error fetching customer from address {address_name}: {str(e)}\n{frappe.get_traceback()}",
            title="Get Customer from Address Error"
        )
        return {
            "customer": None
        }
