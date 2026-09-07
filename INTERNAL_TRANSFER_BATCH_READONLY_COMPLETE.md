# Internal Transfer - Batch Read-Only Implementation

## Status: ✅ COMPLETE

## Date: 2026-05-22

---

## Overview
Implemented batch field read-only functionality for Internal Purchase Receipts created from Internal Purchase Orders. When a Purchase Receipt is created for an internal transfer, the batch numbers are auto-populated from the Pick List and made read-only to prevent manual changes.

---

## Implementation Details

### 1. Backend - Batch Population (Already Implemented)
**File:** `kindlife_app/custom_scripts/purchase_receipt.py`

**Function:** `populate_batch_from_pick_list(doc, method=None)`
- Runs on `onload` event (registered in hooks.py)
- Fetches batch data from Pick List via Sales Order → Purchase Order link
- Auto-populates `batch_no` field in Purchase Receipt items
- Sets `doc.flags.batches_from_pick_list = True` to indicate batches are from Pick List

**Hook Registration:** `kindlife_app/hooks.py` (Line 237)
```python
"Purchase Receipt": {
    "onload": "kindlife_app.custom_scripts.purchase_receipt.populate_batch_from_pick_list",
}
```

---

### 2. Frontend - Batch Read-Only (NEW Implementation)
**File:** `kindlife_app/public/js/purchase_receipt.js`

#### A. Refresh Event Handler (Lines 38-41)
```javascript
// Make batch field read-only for Internal Purchase Receipts
if (frm.doc.is_internal_supplier && frm.doc.items && frm.doc.items.length > 0) {
  make_internal_pr_batch_readonly(frm);
}
```

**Logic:**
- Checks if Purchase Receipt is for internal supplier
- Checks if items exist
- Calls `make_internal_pr_batch_readonly()` function

#### B. Make Batch Read-Only Function (Lines 905-923)
```javascript
function make_internal_pr_batch_readonly(frm) {
    // Check if batches were populated from Pick List
    if (!frm.doc.flags || !frm.doc.flags.batches_from_pick_list) {
        return;
    }
    
    // Make batch_no field read-only in items grid
    frm.fields_dict.items.grid.update_docfield_property('batch_no', 'read_only', 1);
    
    // Refresh the grid to apply changes
    frm.refresh_field('items');
    
    // Show info message
    if (!frm.is_new() && frm.doc.docstatus === 0) {
        frappe.show_alert({
            message: __('Batch numbers are auto-populated from Pick List and cannot be changed'),
            indicator: 'blue'
        }, 5);
    }
}
```

**Features:**
- Verifies `batches_from_pick_list` flag is set (ensures batches came from Pick List)
- Makes `batch_no` field read-only in items grid
- Shows blue alert message to inform user
- Only shows alert for Draft documents (not new or submitted)

---

## Complete Flow

### Business Process
1. **Sales Order** (Internal Customer, Company A) → Create Pick List
2. **Pick List** → Scan serials/batches → Submit
3. **Sales Order** → Create Internal Purchase Order (Company B)
4. **Purchase Order** → Line items are read-only (already implemented)
5. **Purchase Order** → Create Purchase Receipt (GRN)
6. **Purchase Receipt** → Batches auto-populated from Pick List ✅
7. **Purchase Receipt** → Batch field is read-only ✅
8. User enters actual received qty (can be less due to damage)
9. Generate NEW serials for destination warehouse (future enhancement)

### Technical Flow
```
Backend (onload):
  populate_batch_from_pick_list()
    ↓
  Fetch Sales Order from PO
    ↓
  Get Pick List batch data
    ↓
  Auto-populate batch_no in PR items
    ↓
  Set flag: batches_from_pick_list = True

Frontend (refresh):
  Check: is_internal_supplier && items exist
    ↓
  make_internal_pr_batch_readonly()
    ↓
  Check: batches_from_pick_list flag
    ↓
  Make batch_no field read-only
    ↓
  Show alert message
```

---

## Files Modified

### Backend
1. `kindlife_app/api/internal_transfer.py` - Internal transfer API functions
2. `kindlife_app/custom_scripts/purchase_receipt.py` - Batch population logic
3. `kindlife_app/hooks.py` - Hook registration

### Frontend
1. `kindlife_app/public/js/sales_order.js` - Internal PO validation
2. `kindlife_app/public/js/purchase_order.js` - Read-only items grid
3. `kindlife_app/public/js/purchase_receipt.js` - **Batch read-only logic** ✅

---

## Testing Instructions

### Test Scenario: Internal Transfer with Batch Read-Only
1. Create Sales Order with internal customer (Company A)
2. Create Pick List from Sales Order
3. Scan serials/batches in Pick List
4. Submit Pick List
5. Go back to Sales Order
6. Click "Internal Purchase Order" button
7. Verify PO is created with read-only line items
8. Submit the Purchase Order
9. Click "Create Purchase Receipt" button
10. **Expected Results:**
    - Batch numbers should be auto-populated from Pick List ✅
    - Batch field should be read-only (cannot edit) ✅
    - Blue alert message should appear: "Batch numbers are auto-populated from Pick List and cannot be changed" ✅
11. Enter actual received quantity
12. Save and submit Purchase Receipt

---

## Frappe-First Compliance

All implementations use Frappe built-in utilities:
- ✅ `frappe.call()` for API calls
- ✅ `frappe.db.get_value()` for database queries
- ✅ `frappe.get_doc()` for document operations
- ✅ `@frappe.whitelist()` for API endpoints
- ✅ `frappe.msgprint()`, `frappe.show_alert()` for UI
- ✅ `frappe.log_error()` for error logging
- ✅ `frm.set_df_property()` for field properties
- ✅ `frm.refresh_field()` for UI refresh

No external packages used. ✅

---

## Conclusion

The batch read-only functionality for Internal Purchase Receipts is now **COMPLETE**. Batches are auto-populated from Pick List and made read-only to prevent manual changes, ensuring data integrity in internal transfers.

**Status:** ✅ Ready for Testing
**Branch:** `item_lock_scanning`
**Date:** 2026-05-22
