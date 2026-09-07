# Sales Order Custom API Analysis

## Overview
This document provides a comprehensive analysis of all custom-built APIs related to **fetching and managing Sales Order information** in the kindlife_app codebase.

---

## 📍 API Endpoints for Fetching Sales Order Information

### 1. **Get Sales Order by PO Number** (B2B)
**File:** `kindlife_app/api/b2b/sales_order.py`  
**Function:** `get_sales_order_by_po(po_no)`  
**HTTP Method:** GET  
**Access:** `@frappe.whitelist(methods=['GET'])`

**Purpose:**  
Fetch Sales Order details using the Purchase Order (PO) number.

**Parameters:**
- `po_no` (string): Purchase Order number

**Returns:**
```json
{
    "name": "SO-24-25-000209",
    "customer": "Customer Name",
    "grand_total": 10000.00,
    "status": "Draft/Submitted/Completed",
    "transaction_date": "2024-12-01",
    "delivery_date": "2024-12-10",
    "price_list": "Standard Selling",
    "po_date": "2024-11-30",
    "shipping_address_name": "ADDR-00001",
    "items": [
        {
            "item_code": "ITM-001",
            "item_name": "Product Name",
            "qty": 10,
            "rate": 100.00,
            "amount": 1000.00
        }
    ]
}
```

**Usage Example:**
```bash
GET /api/method/kindlife_app.api.b2b.sales_order.get_sales_order_by_po?po_no=PO-2024-001
```

---

### 2. **Get Order Status** (CS Cart Integration)
**File:** `kindlife_app/api/sales_order.py`  
**Function:** `get_order_status(order_id)`  
**HTTP Method:** POST/GET  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Get the status of a CS Cart order by its order ID.

**Parameters:**
- `order_id` (string): CS Cart Order ID

**Returns:**
```json
{
    "status": "success",
    "order_id": "CS-12345",
    "sales_order": "SO-24-25-000209",
    "sales_order_status": "To Deliver and Bill",
    "order_total": 5000.00,
    "delivered_qty": 0,
    "billed_qty": 0
}
```

**Usage Example:**
```bash
POST /api/method/kindlife_app.api.sales_order.get_order_status
{
    "order_id": "CS-12345"
}
```

---

### 3. **Get Draft Pick Lists Count**
**File:** `kindlife_app/api/sales_order.py`  
**Function:** `get_draft_pick_lists_count(sales_order)`  
**HTTP Method:** POST/GET  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Get count of draft and submitted Pick Lists linked to a Sales Order.

**Parameters:**
- `sales_order` (string): Sales Order ID

**Returns:**
```json
{
    "draft_count": 2,
    "submitted_count": 1,
    "total_count": 3
}
```

---

### 4. **Get Pick List Batch/Serial Data** (Internal Transfer)
**File:** `kindlife_app/api/internal_transfer.py`  
**Function:** `get_pick_list_batch_serial_data(sales_order)`  
**HTTP Method:** POST/GET  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Retrieve batch and serial number data from Pick Lists associated with a Sales Order.

**Parameters:**
- `sales_order` (string): Sales Order ID

**Returns:**
```json
{
    "status": "success",
    "sales_order": "SO-24-25-000209",
    "pick_lists": [
        {
            "pick_list": "PL-00001",
            "items": [
                {
                    "item_code": "ITM-001",
                    "batch_no": "BATCH-001",
                    "serial_nos": ["SN-001", "SN-002"],
                    "qty": 2
                }
            ]
        }
    ]
}
```

---

### 5. **Get Internal PO Sales Order**
**File:** `kindlife_app/api/internal_transfer.py`  
**Function:** `get_internal_po_sales_order(purchase_order)`  
**HTTP Method:** POST/GET  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Get the linked Sales Order for an Internal Purchase Order.

**Parameters:**
- `purchase_order` (string): Purchase Order ID

**Returns:**
```json
{
    "sales_order": "SO-24-25-000209"
}
```

---

### 6. **Check Pick List Exists**
**File:** `kindlife_app/api/internal_transfer.py`  
**Function:** `check_pick_list_exists(sales_order)`  
**HTTP Method:** POST/GET  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Check if Pick Lists exist for a given Sales Order.

**Parameters:**
- `sales_order` (string): Sales Order ID

**Returns:**
```json
{
    "exists": true,
    "pick_lists": ["PL-00001", "PL-00002"],
    "count": 2
}
```

---

## 📝 API Endpoints for Creating/Modifying Sales Orders

### 7. **Create Sales Order** (CS Cart Integration)
**File:** `kindlife_app/api/sales_order.py`  
**Function:** `create_sales_order(data)`  
**HTTP Method:** POST  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Create a B2C Sales Order from CS Cart with automatic warehouse assignment and pick list creation.

**Parameters:**
```json
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
            "qty": 2
        }
    ]
}
```

**Returns:**
```json
{
    "status": "success",
    "message": "Sales Order created successfully",
    "sales_order": "SO-24-25-000209",
    "sales_order_id": "SO-24-25-000209",
    "order_total": 5000.00
}
```

---

### 8. **Create Pick Lists for Sales Order**
**File:** `kindlife_app/api/sales_order.py`  
**Function:** `create_pick_lists_for_sales_order(sales_order_id, items)`  
**HTTP Method:** POST  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Create Pick Lists for a Sales Order and return warehouse/supplier details with logistic partner information.

**Parameters:**
```json
{
    "sales_order_id": "SO-24-25-000209",
    "items": [
        {
            "item_code": "ITM-001",
            "qty": 2
        }
    ]
}
```

**Returns:**
```json
{
    "status": "success",
    "message": "Pick Lists created successfully",
    "sales_order": "SO-24-25-000209",
    "order_id": "CS-12345",
    "flagship_items": [
        {
            "product_code": "PROD-001",
            "item_code": "ITM-001",
            "product_id": "12345",
            "qty": 2,
            "supplier": "Brand Supplier",
            "supplier_id": "SUP-001",
            "supplier_address": "123 Supplier St, City",
            "custom_default_logistic_partner": "DHL",
            "partner_id": "DHL-001",
            "shipment_id": "SHIP-001"
        }
    ],
    "pick_list_items": [
        {
            "product_code": "PROD-002",
            "item_code": "ITM-002",
            "product_id": "67890",
            "qty": 1,
            "supplier": "WH-Delhi",
            "supplier_address": "Warehouse Address",
            "pick_list": "PL-00001",
            "custom_default_logistic_partner": "BlueDart",
            "partner_id": "BD-001",
            "shipment_id": "SHIP-002"
        }
    ],
    "pick_lists": ["PL-00001", "PL-00002"],
    "errors": {
        "flagship_items": [],
        "pick_list_items": []
    }
}
```

---

### 9. **Create B2B Sales Order**
**File:** `kindlife_app/api/b2b/sales_order.py`  
**Function:** `create_b2b_sales_order(data)`  
**HTTP Method:** POST  
**Access:** `@frappe.whitelist(methods=['POST'])`

**Purpose:**  
Create a B2B Sales Order with customer and item information.

**Parameters:**
```json
{
    "customer": "CUST-00123",
    "price_list": "Standard Selling",
    "shipping_address_name": "ADDR-00001",
    "billing_address_name": "ADDR-00002",
    "po_no": "PO-2024-001",
    "po_date": "2024-12-02",
    "delivery_date": "2024-12-10",
    "items": [
        {
            "item_code": "ITM-001",
            "qty": 10,
            "rate": 100.00
        }
    ]
}
```

---

### 10. **Create B2B Sales Order from Buyer SKUs**
**File:** `kindlife_app/api/b2b/sales_order.py`  
**Function:** `create_b2b_sales_order_from_buyer_skus(...)`  
**HTTP Method:** POST  
**Access:** `@frappe.whitelist(methods=['POST'])`

**Purpose:**  
Convenience API that combines customer lookup via address and item lookup via buyer SKUs to create a B2B Sales Order.

**Parameters:**
```json
{
    "gstin": "29ABCDE1234F1Z5",
    "city": "Bangalore",
    "buyers_skus": ["SKU-001", "SKU-002"],
    "items_with_qty": {
        "SKU-001": 10,
        "SKU-002": 5
    },
    "po_no": "PO-2024-001",
    "po_date": "2024-12-02",
    "delivery_date": "2024-12-10"
}
```

---

### 11. **Handle Order Event** (Cancellation/Return/Replacement)
**File:** `kindlife_app/api/order_management.py`  
**Function:** `handle_order_event(data)`  
**HTTP Method:** POST  
**Access:** `@frappe.whitelist(allow_guest=False)`

**Purpose:**  
Handle order cancellations, returns, and replacements from CS Cart.

**Parameters:**
```json
{
    "event_type": "cancellation",
    "sales_order_id": "SO-24-25-000209",
    "reason": "Customer requested cancellation",
    "items": [
        {
            "item_code": "ITM-001",
            "qty": 1
        }
    ]
}
```

**Returns:**
```json
{
    "status": "success",
    "message": "Items updated successfully"
}
```

---

### 12. **Store Shipment PDF**
**File:** `kindlife_app/api/sales_order.py`  
**Function:** `store_shipment_pdf(...)`  
**HTTP Method:** POST  
**Access:** `@frappe.whitelist()`

**Purpose:**  
Store shipment PDF and update AWB/tracking information on Sales Order items.

**Parameters:**
```json
{
    "sales_order_id": "SO-24-25-000209",
    "shipment_id": "SHIP-001",
    "shipped_items": ["ITM-001"],
    "pdf_file": "base64_encoded_pdf",
    "carrier": "DHL",
    "tracking_number": "TRK-12345",
    "awb_number": "AWB-12345"
}
```

---

## 🔍 Additional Helper Functions

### Get Item Price for Sales Order
**File:** `kindlife_app/api/item_price.py`  
**Function:** `get_item_price_for_sales_order(item_code, price_list, customer, transaction_date, uom)`  
**Purpose:** Get item price details for sales order line items.

### Recalculate Margins
**File:** `kindlife_app/services/margin_engine.py`  
**Function:** `recalculate_margins(sales_order_name)`  
**Purpose:** Recalculate profit margins for a Sales Order.

---

## 🎯 Key API Categories

### 📖 **Read/Fetch Operations:**
1. `get_sales_order_by_po()` - Fetch SO by PO number (B2B)
2. `get_order_status()` - Get CS Cart order status
3. `get_draft_pick_lists_count()` - Count pick lists
4. `get_pick_list_batch_serial_data()` - Get batch/serial info
5. `get_internal_po_sales_order()` - Get linked SO for internal PO
6. `check_pick_list_exists()` - Check if pick lists exist

### ✏️ **Create/Modify Operations:**
1. `create_sales_order()` - Create B2C SO from CS Cart
2. `create_pick_lists_for_sales_order()` - Create pick lists
3. `create_b2b_sales_order()` - Create B2B SO
4. `create_b2b_sales_order_from_buyer_skus()` - Create B2B SO from buyer SKUs
5. `handle_order_event()` - Handle cancellation/return/replacement
6. `store_shipment_pdf()` - Store shipment documents

---

## 📊 Integration Points

### CS Cart (B2C):
- Create orders with automatic warehouse assignment
- Handle order events (cancel/return/replace)
- Store shipment tracking and PDFs
- Webhook endpoint for order status updates

### B2B:
- Create orders from customer address + buyer SKUs
- Fetch orders by PO number
- Support for custom pricing and addresses

### Internal Transfer:
- Pick list and batch/serial tracking
- Link internal POs to Sales Orders
- Stock reservation and fulfillment

---

## 🔐 Authentication
All APIs use Frappe's built-in authentication:
- `@frappe.whitelist()` - Requires logged-in user
- `@frappe.whitelist(allow_guest=True)` - Allows guest access
- `@frappe.whitelist(methods=['GET'])` - Restricts to specific HTTP methods

---

## 📝 Notes
- Most APIs return JSON responses with `status`, `message`, and relevant data
- Error handling includes rollback and error logging
- Pick list creation is automated for warehouse-fulfilled items
- Brand-fulfilled items are tracked separately with supplier information
- Logistic partner assignment is automatic based on warehouse/supplier configuration

---

**Generated:** July 2, 2026  
**Codebase:** kindlife_app ERP application
