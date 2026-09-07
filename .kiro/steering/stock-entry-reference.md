---
title: Stock Entry System Reference
inclusion: manual
tags: [stock-entry, barcode, serial-scanning, inventory]
---

# Stock Entry System - Complete Reference Guide

## 📋 Overview

This document provides a comprehensive reference for the Stock Entry system, covering both frontend (JavaScript) and backend (Python) components. Use this guide when working on Stock Entry features, barcode generation, or serial number scanning functionality.

---

## 🗂️ File Structure

### Frontend Files
- **`kindlife_app/public/js/stock_entry.js`** (873 lines)
  - Main client-side logic for Stock Entry form
  - Serial number scanning system
  - Barcode generation UI
  - Custom form behaviors

### Backend Files
- **`kindlife_app/custom_scripts/stock_entry.py`**
  - Extends ERPNext StockEntry class
  - Validation logic (batch matching, scanning completion, duplicates)
  - Purchase Receipt workflow integration
  - Bundle serial data API

- **`kindlife_app/api/barcode_download.py`**
  - PDF barcode generation
  - Serial number barcode printing
  - File attachment management

- **`kindlife_app/api/stock_entry.py`**
  - Purchase Order lookup from Purchase Receipt
  - Navigation helper APIs

### Configuration
- **`kindlife_app/hooks.py`**
  - Line 64: `"Stock Entry":"public/js/stock_entry.js"` (doctype_js)
  - Line 157: Permission query override
  - Line 171: has_permission override
  - Line 195: `override_doctype_class` - StockEntryExtends

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    STOCK ENTRY SYSTEM                        │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
         ┌──────▼──────┐            ┌──────▼──────┐
         │  FRONTEND   │            │   BACKEND   │
         │  (JS - 873) │            │  (Python)   │
         └──────┬──────┘            └──────┬──────┘
                │                           │
    ┌───────────┼───────────┐              │
    │           │           │              │
┌───▼───┐  ┌───▼───┐  ┌───▼───┐      ┌───▼────────────┐
│ Form  │  │Serial │  │Barcode│      │ StockEntry     │
│Events │  │Scanner│  │  UI   │      │ Extends        │
└───────┘  └───┬───┘  └───┬───┘      └───┬────────────┘
               │          │              │
               │          │         ┌────┼────┐
               │          │         │    │    │
               │          │    ┌────▼┐ ┌─▼──┐ │
               │          └────►API  │ │API │ │
               │               │B/C  │ │SE  │ │
               └───────────────►Down │ └────┘ │
                               └─────┘        │
                                              │
                                         Validation
                                         Workflow
                                         Bundle Data
```

---

## 📦 JavaScript Components (stock_entry.js)

### 1. Global Functions

#### `frappe.trigger_barcode_api(event, child_docname, parent_docname)`
**Purpose:** Generate and download barcode PDFs for a Stock Entry Detail row

**Flow:**
```javascript
1. Prevent event propagation (stops modal opening)
2. Validate document is saved
3. Validate row has serial data (serial_no OR serial_and_batch_bundle)
4. Call API: kindlife_app.api.barcode_download.download_row_barcodes
5. Decode base64 PDF response
6. Open in new window and trigger print dialog
```

**API Called:**
- `kindlife_app.api.barcode_download.download_row_barcodes`
- Args: `{stock_entry_name, row_name}`
- Returns: `{pdf_base64, filename}`

---

### 2. Form Event Handlers

#### Stock Entry Form Events

##### `onload(frm)`
- Initializes `StockEntrySerialScanner` instance
- Stored in `frm.serial_scanner`

##### `check_scanning_status(frm)`
- Checks if all items have `custom_scanned_qty == qty`
- Updates dashboard headline with green checkmark if complete

##### `custom_skip_barcode_scanning(frm)`
- Bulk operation to skip scanning
- Copies `serial_no` → `custom_scanned_serial_no`
- Sets `custom_scanned_qty = qty` for all rows

##### `setup(frm)`
- Runs once on form initialization
- Calls: `apply_barcode_meta_formatter(frm)`
- Calls: `setup_barcode_row_handlers(frm)`

##### `refresh(frm)`
- Re-applies formatters and handlers
- Removes unwanted standard buttons (Material Request, Purchase Invoice, etc.)
- Adds "Go To" dropdown (Purchase Receipt → Purchase Order navigation)
- Adds "New Putaway Rule" button
- Re-adds serial scanning buttons

##### `custom_scan_serial_no(frm)` ⭐ **KEY SCANNING TRIGGER**
```javascript
if (frm.doc.custom_scan_serial_no && frm.serial_scanner) {
    frm.serial_scanner.process_serial_scan(frm.doc.custom_scan_serial_no);
}
```
- Triggered when barcode scanner inputs data
- Delegates to scanner class for processing

#### Stock Entry Detail (Child Table) Events

##### `custom_scanned_qty(frm, cdt, cdn)`
- Refreshes grid when scanned quantity changes
- Triggers `check_scanning_status()`

##### `serial_and_batch_bundle(frm, cdt, cdn)`
- Reloads serial data when bundle changes
- Calls: `frm.serial_scanner.load_local_serial_data()`

---

### 3. StockEntrySerialScanner Class

**Purpose:** Manages real-time serial number scanning with validation

#### Data Structures

```javascript
{
  // Configuration
  scan_field_name: "custom_scan_serial_no",
  scanned_qty_field: "custom_scanned_qty",
  scanned_serial_field: "custom_scanned_serial_no",
  
  // Caches (Maps)
  serial_cache: Map(),    // serial_no → {serial_no, item_code, item_idx, batch_no, warehouse}
  row_serials: Map(),     // item_idx → [serial_nos]
  item_serials: Map(),    // item_code → [serial_nos]
  
  // Audio feedback
  success_sound: "submit",
  fail_sound: "error"
}
```

#### Key Methods

##### `async load_local_serial_data()` 🔑 **CRITICAL**
**Purpose:** Load and cache all serial numbers from form items and bundles

**Data Sources:**
1. **Text Field:** `item.serial_no` (newline-separated)
2. **Bundle API:** `kindlife_app.custom_scripts.stock_entry.get_bundle_serial_data`

**Process:**
```javascript
1. Clear all caches
2. Identify bundles to fetch
3. Call API to get bundle data
4. For each item row:
   a. Parse serial_no text field
   b. Merge bundle data
   c. Build serial_cache (serial → details)
   d. Build row_serials (idx → serials)
   e. Build item_serials (item_code → serials)
```

**API Called:**
- `kindlife_app.custom_scripts.stock_entry.get_bundle_serial_data`
- Args: `{stock_entry_name}`
- Returns: `{bundle_name: [{serial_no, batch_no}, ...]}`

##### `async process_serial_scan(scanned_value)` 🎯 **CORE LOGIC**
**Purpose:** Process a single scanned serial number with validation

**Validation Chain:**
```
Scanned Value
  ↓
Exists in Cache? → NO → FAIL (not found)
  ↓ YES
Has Matching Row? → NO → FAIL (no row)
  ↓ YES
Row Exists? → NO → FAIL (row not found)
  ↓ YES
Belongs to Row? → NO → FAIL (wrong row)
  ↓ YES
Already Scanned? → YES → FAIL (duplicate)
  ↓ NO
✅ ADD TO SCANNED LIST
```

**Feedback:**
- Success: Green alert + success sound
- Failure: Red/Orange alert + fail sound

##### `add_scanning_buttons()`
Adds custom buttons to toolbar:

**Serial Scanning Dropdown:**
- "Validate All Scanned Serials"
- "Clear All Scanned Data" (draft only)
- "Show Scanning Progress"
- "Reload Serial Data"

**Row Locking Dropdown:** (NEW - May 2026)
- "Release All My Locks"
- "Show Locked Rows"
- "Refresh Lock Status"

See `.kiro/steering/row-locking-system.md` for complete row locking documentation

##### `async validate_all_scanned_serials()`
**Purpose:** Validate scanned serials against expected serials

**Output Categories:**
- ✅ Valid serials (in expected list)
- ❌ Invalid serials (not in expected list)
- ⏳ Missing serials (expected but not scanned)

##### `clear_all_scanned_data()`
**Purpose:** Selective clearing of scanned data

**Features:**
- Shows dialog with checkboxes for each row
- "Select All" functionality
- Displays scanned progress badges
- Clears only selected rows

##### `async show_scanning_progress()`
**Purpose:** Display detailed scanning progress report

**Shows:**
- Overall progress percentage
- Per-row progress bars
- Color-coded status (green/yellow/red)
- Icons (✅/⏳/❌)

---

### 4. Helper Functions

#### `add_go_to_dropdown_se(frm)`
**Purpose:** Add navigation buttons to related documents

**Buttons Added:**
- "Purchase Receipt" (if `reference_purchase_receipt` exists)
- "Purchase Order" (fetched via API)

**API Called:**
- `kindlife_app.api.stock_entry.get_purchase_order_from_receipt`
- Args: `{purchase_receipt, item_code}`
- Returns: `{purchase_order}`

#### `apply_barcode_meta_formatter(frm)`
**Purpose:** Apply custom formatters to grid fields

**Formatters:**
1. **`custom_generate_barcodes`**
   - Returns: `<span class="kl-barcode-btn">BARCODES</span>`
   - Clickable button in grid

2. **`custom_scanned_qty`**
   - If `scanned_qty == qty`: Green highlighted cell
   - Else: Plain display

**Triple-Threat Injection:**
1. Global Meta Map
2. Grid Fields Map
3. Force Refresh (300ms delay)

#### `setup_barcode_row_handlers(frm)`
**Purpose:** Setup click handlers for barcode buttons

**Handlers:**
1. **Generate Barcode Button (`.kl-barcode-btn`)**
   - Prevents event propagation
   - Extracts row name from `data-name` attribute
   - Calls `frappe.trigger_barcode_api()`

2. **Open Barcodes Link (`.kl-barcode-link`)**
   - Opens PDF in new tab

**Event Phase:** Capture phase (true) - intercepts before bubbling

#### `set_warehouse_in_se(frm)`
**Purpose:** Filter warehouse dropdown based on custom_type

**Query:**
```javascript
frm.set_query("t_warehouse", "items", function(doc, cdt, cdn) {
    if (doc.custom_type) {
        return {
            filters: {
                "custom_type": doc.custom_type
            }
        };
    }
});
```

---

## 🐍 Python Components

### 1. StockEntryExtends Class (custom_scripts/stock_entry.py)

**Extends:** `erpnext.stock.doctype.stock_entry.stock_entry.StockEntry`

#### Lifecycle Hooks

##### `on_submit()`
```python
1. validate_batch_item_match()      # Strict batch ownership check
2. validate_scanning_complete()     # Ensure all serials scanned
3. super().on_submit()              # Call parent
4. update_related_pr()              # Update PR workflow state
```

##### `on_cancel()`
```python
1. update_related_pr()              # Revert PR workflow state
2. super().on_cancel()              # Call parent
```

##### `before_validate()`
```python
1. Apply putaway rules (if enabled)
2. validate_duplicate_rows()        # Prevent duplicate item/batch/warehouse
```

#### Validation Methods

##### `validate_batch_item_match()`
**Purpose:** Ensure batch belongs to the correct item

**Logic:**
```python
For each item with batch_no:
  1. Get batch owner (item)
  2. If owner exists and owner != current item:
     a. Search for batch with same custom_batch_no for current item
     b. If found: Suggest existing batch
     c. If not found: Suggest creating new batch
  3. If mismatches found: Throw error with HTML table
```

**Error Display:**
- HTML table showing:
  - Row number
  - Item code
  - Wrong batch
  - Suggestion (Use existing / Create new)

##### `validate_duplicate_rows()`
**Purpose:** Prevent multiple rows with same item/batch/warehouse

**Exception:** Skipped when putaway rule is applied and SE is linked to PR

**Error:** Throws if duplicates found

##### `validate_scanning_complete()`
**Purpose:** Ensure all serials are scanned before submit

**Skip Conditions:**
- `custom_skip_barcode_scanning` is checked
- Item is not serialized and has no bundle

**Validation:**
```python
For each item:
  If qty != custom_scanned_qty:
    Add to mismatches
    
If mismatches:
  Show HTML table with:
    - Row, Item, Required Qty, Scanned Qty
```

##### `update_related_pr()`
**Purpose:** Update Purchase Receipt workflow state

**Logic:**
```python
If SE has reference_purchase_receipt:
  On Submit: Set PR workflow_state = "Completed"
  On Cancel: Set PR workflow_state = "Pending Putaway"
```

#### API Methods

##### `@frappe.whitelist() get_bundle_serial_data(stock_entry_name)`
**Purpose:** Fetch all serial/batch entries for all bundles in a Stock Entry

**Returns:**
```python
{
  "bundle_name_1": [
    {"serial_no": "SN001", "batch_no": "B1"},
    {"serial_no": "SN002", "batch_no": "B1"}
  ],
  "bundle_name_2": [...]
}
```

**Process:**
1. Get all bundles for Stock Entry
2. Get all Serial and Batch Entries for those bundles
3. Group by parent (bundle name)

---

### 2. Barcode Download API (api/barcode_download.py)

#### Main API Method

##### `@frappe.whitelist() download_row_barcodes(stock_entry_name, row_name)`
**Purpose:** Generate barcode PDF for a single Stock Entry Detail row

**Returns:**
```python
{
  "pdf_base64": "base64_encoded_pdf_content",
  "filename": "Barcodes_ITEM-CODE_SE-NAME.pdf"
}
```

**Process:**
1. Validate inputs
2. Get row data (item_code, warehouse, batch_no, serial_no, bundle)
3. Fetch serial data using `_get_serial_data_from_row()`
4. Generate PDF using `generate_barcode_pdf_from_row()`
5. Return base64-encoded PDF

#### Helper Methods

##### `_get_serial_data_from_row(row)`
**Purpose:** Orchestrator to get serial/batch data from text field or bundle

**Returns:** `[{'serial_no': '...', 'batch_no': '...'}, ...]`

**Sources:**
1. `_get_serials_from_text(row)` - Parse serial_no text field
2. `_get_serials_from_bundle(bundle_name)` - Query bundle entries

##### `generate_barcode_pdf_from_row(serial_data, label_data)`
**Purpose:** Generate PDF with Code128 barcodes (1 per page)

**Page Layout:**
```
┌─────────────────────────────┐
│                             │
│   ITEM-CODE - WAREHOUSE     │ ← Top label (Bold, 9pt)
│                             │
│   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    │ ← Barcode (Code128)
│                             │
│   BATCH-NO - SERIAL-NO      │ ← Bottom label (8pt)
│                             │
└─────────────────────────────┘
```

**Dimensions:**
- Page: 3" × 1.7"
- Barcode height: 0.6"
- Margins: 0.2"

**Library:** ReportLab (code128 barcode)

---

### 3. Stock Entry API (api/stock_entry.py)

##### `@frappe.whitelist() get_purchase_order_from_receipt(purchase_receipt, item_code)`
**Purpose:** Get Purchase Order linked to a Purchase Receipt for a specific item

**Returns:**
```python
{"purchase_order": "PO-00001"}  # or None
```

**Process:**
1. Query Purchase Receipt Item
2. Filter by parent and item_code
3. Return purchase_order field

**Error Handling:**
- Returns `{"purchase_order": None}` on permission errors
- Logs errors to Error Log

---

## 🔗 Integration Points

### Frontend → Backend API Calls

| JavaScript Method | Python API | Purpose |
|------------------|------------|---------|
| `frappe.trigger_barcode_api()` | `barcode_download.download_row_barcodes` | Generate barcode PDF |
| `load_local_serial_data()` | `stock_entry.get_bundle_serial_data` | Fetch bundle serials |
| `add_go_to_dropdown_se()` | `stock_entry.get_purchase_order_from_receipt` | Get linked PO |
| `refresh()` | `putaway_rule.apply_putaway_rule` | Apply putaway rules |

### Backend → Frontend Flow

```
User Scans Barcode
  ↓
custom_scan_serial_no field changes
  ↓
JS: process_serial_scan()
  ↓
Validates against serial_cache (loaded from Python API)
  ↓
Updates custom_scanned_serial_no & custom_scanned_qty
  ↓
On Submit: Python validates scanning complete
  ↓
If valid: Submit succeeds
```

---

## 🎯 Key Custom Fields

### Stock Entry (Parent)
- `custom_scan_serial_no` - Text field for barcode scanner input
- `custom_skip_barcode_scanning` - Checkbox to bypass scanning

### Stock Entry Detail (Child)
- `custom_scanned_qty` - Int - Number of serials scanned
- `custom_scanned_serial_no` - Long Text - Newline-separated scanned serials
- `custom_generate_barcodes` - Data - Formatted as button in grid

---

## 🔧 Common Workflows

### 1. Serial Number Scanning Workflow

```
1. User opens Stock Entry
   └─ onload: Initialize StockEntrySerialScanner
   
2. Scanner loads serial data
   └─ load_local_serial_data()
      ├─ Parse serial_no text fields
      └─ Fetch bundle data via API
      
3. User scans barcode
   └─ custom_scan_serial_no field updated
   └─ process_serial_scan()
      ├─ Validate serial exists
      ├─ Find appropriate row
      ├─ Check not already scanned
      └─ Add to scanned list
      
4. User submits
   └─ Python: validate_scanning_complete()
      └─ Ensure all serials scanned
```

### 2. Barcode Generation Workflow

```
1. User clicks "BARCODES" button in grid
   └─ setup_barcode_row_handlers() intercepts click
   
2. Call frappe.trigger_barcode_api()
   ├─ Validate document saved
   ├─ Validate row has serial data
   └─ Call Python API
   
3. Python: download_row_barcodes()
   ├─ Get row data
   ├─ Fetch serials (text or bundle)
   ├─ Generate PDF with Code128 barcodes
   └─ Return base64 PDF
   
4. JavaScript receives PDF
   ├─ Decode base64
   ├─ Create Blob
   ├─ Open in new window
   └─ Trigger print dialog
```

### 3. Batch Validation Workflow

```
1. User enters batch in Stock Entry Detail
   
2. On Submit: validate_batch_item_match()
   ├─ For each item with batch:
   │  ├─ Get batch owner (item)
   │  └─ If owner != current item:
   │     ├─ Search for batch with same custom_batch_no
   │     └─ Add to mismatches
   │
   └─ If mismatches: Show error table with suggestions
```

---

## 🚨 Important Notes

### Performance Considerations
- Serial cache is loaded once and reused
- Bundle API call only made if bundles exist
- Grid formatters use triple-injection for reliability

### Security
- All Python APIs use `@frappe.whitelist()`
- Permission queries defined in hooks.py
- File attachments respect Frappe permissions

### Debugging Tips
1. **Scanner not working:**
   - Check `frm.serial_scanner` exists
   - Check `serial_cache.size` in console
   - Verify `custom_scan_serial_no` field exists

2. **Barcode generation fails:**
   - Check document is saved
   - Verify row has serial_no or serial_and_batch_bundle
   - Check Error Log for Python errors

3. **Validation errors:**
   - Check `custom_skip_barcode_scanning` checkbox
   - Verify batch ownership in Batch doctype
   - Check for duplicate rows

### Extension Points
- Add new validation: Override `before_validate()` or `validate()`
- Custom barcode format: Modify `generate_barcode_pdf_from_row()`
- Additional scanner features: Extend `StockEntrySerialScanner` class

---

## 📚 Related Files

### Row Locking System (NEW - May 2026)
- **`.kiro/steering/row-locking-system.md`** - Complete reference for row locking
- **`kindlife_app/api/row_locking.py`** - Backend lock management API
- Row locking prevents concurrent editing conflicts during serial scanning
- Uses Redis (frappe.cache()) for fast, temporary locks with auto-expiry
- See row-locking-system.md for complete documentation

### Also Check
- `kindlife_app/public/js/utils.js` - Contains `set_custom_type_based_on_role()`
- `kindlife_app/custom_scripts/putaway_rule.py` - Putaway rule logic
- `kindlife_app/custom_scripts/purchase_receipt.py` - PR → SE flow

### Permissions
- `kindlife_app/services/permissions/doctypes/stock_entry.py`
  - `permission_query()` - Filter records by user
  - `has_permission()` - Check user access

---

## 🎓 Code Examples

### Adding a New Scanner Button

```javascript
// In StockEntrySerialScanner.add_scanning_buttons()
this.frm.add_custom_button(__('My Custom Action'), async () => {
    await this.my_custom_method();
}, __('Serial Scanning'));
```

### Adding Custom Validation

```python
# In StockEntryExtends class
def validate_my_custom_rule(self):
    for item in self.items:
        if item.custom_field:
            # Your validation logic
            pass
    
# Call in before_validate() or validate()
def before_validate(self):
    super().before_validate()
    self.validate_my_custom_rule()
```

### Calling Custom API from JS

```javascript
frappe.call({
    method: 'kindlife_app.api.my_module.my_method',
    args: {
        stock_entry_name: frm.doc.name
    },
    callback: function(r) {
        if (r.message) {
            console.log(r.message);
        }
    }
});
```

---

## 📝 Changelog Reference

When modifying Stock Entry code, document changes here:

### Template
```
Date: YYYY-MM-DD
Modified By: [Name]
Files Changed: [List]
Changes:
- [Description]
Reason: [Why]
Testing: [How tested]
```

---

**Last Updated:** 2026-05-07
**Maintained By:** Development Team
**Version:** 1.0.0
