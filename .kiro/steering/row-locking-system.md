---
title: Row Locking System for Stock Entry
description: Complete reference for Redis-based row-level locking system that prevents concurrent editing conflicts during serial number scanning
keywords: row locking, redis, stock entry, serial scanning, multi-user, concurrency, frappe cache
inclusion: manual
created: 2026-05-07
tested: 2026-05-07
status: production
---

# Row Locking System - Stock Entry Serial Scanning

## Overview

**Purpose:** Prevent multiple users from scanning serial numbers on the same Stock Entry row simultaneously, avoiding data conflicts and confusion.

**Technology:** Redis-based locking using `frappe.cache()` (100% Frappe built-in)

**Implementation Date:** May 7, 2026

**Status:** ✅ Tested and Working in Production

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (JavaScript)                 │
│  kindlife_app/public/js/stock_entry.js                  │
│                                                          │
│  StockEntrySerialScanner Class:                         │
│  - load_row_locks()         Load locks from Redis       │
│  - try_lock_row()           Acquire lock before scan    │
│  - release_lock()           Release lock manually       │
│  - start_heartbeat()        Keep lock alive (4 min)     │
│  - start_lock_check()       Poll for changes (30 sec)   │
│  - update_row_lock_ui()     Visual indicators           │
│  - release_all_my_locks()   Bulk release                │
│  - show_locked_rows()       Lock management dialog      │
└─────────────────────────────────────────────────────────┘
                            ↕ frappe.call()
┌─────────────────────────────────────────────────────────┐
│                    BACKEND (Python)                      │
│  kindlife_app/api/row_locking.py                        │
│                                                          │
│  RowLockManager Class:                                  │
│  - acquire_lock()           Try to lock a row           │
│  - release_lock()           Release a lock              │
│  - get_all_locks()          Get all locks for doc       │
│  - refresh_heartbeat()      Extend lock TTL             │
│  - get_active_users()       List active users           │
│  - cleanup_user_locks()     Cleanup on logout           │
│                                                          │
│  Whitelisted API Methods:                               │
│  @frappe.whitelist()                                    │
│  - acquire_row_lock()                                   │
│  - release_row_lock()                                   │
│  - get_all_row_locks()                                  │
│  - refresh_lock_heartbeat()                             │
│  - get_active_users()                                   │
│  - cleanup_my_locks()                                   │
└─────────────────────────────────────────────────────────┘
                            ↕ frappe.cache()
┌─────────────────────────────────────────────────────────┐
│                    REDIS (Cache Layer)                   │
│                                                          │
│  Keys:                                                   │
│  - se_row_lock:{doc}:{idx}     Individual row lock      │
│  - se_active_users:{doc}       Active users set         │
│  - se_user_session:{sid}       User session tracking    │
│                                                          │
│  TTL: 15 minutes (auto-expiry)                          │
└─────────────────────────────────────────────────────────┘
```

---

## How It Works

### User Flow

```
1. User opens Stock Entry
   ↓
2. setup_scanner() called
   ↓
3. load_row_locks() - Fetch existing locks from Redis
   ↓
4. start_lock_check() - Start polling (every 30 sec)
   ↓
5. UI shows locked rows (blue = mine, yellow = others)
   ↓
6. User scans serial number
   ↓
7. process_serial_scan() checks:
   - Is row locked by another user? → BLOCK
   - Is row unlocked? → Try to acquire lock
   - Lock acquired? → Continue scanning
   ↓
8. start_heartbeat() - Keep lock alive (every 4 min)
   ↓
9. User continues scanning same row (lock already held)
   ↓
10. Lock expires after 15 min OR user releases manually
```

### Lock Lifecycle

```
┌──────────────┐
│ Row Unlocked │
└──────┬───────┘
       │ User scans first serial
       ↓
┌──────────────┐
│ Lock Acquired│ ← Redis: se_row_lock:{doc}:{idx}
└──────┬───────┘
       │
       ├─→ Heartbeat every 4 min (refresh TTL)
       │
       ├─→ User continues scanning (lock held)
       │
       └─→ One of:
           ├─→ User releases manually
           ├─→ 15 min inactivity (auto-expire)
           └─→ User closes browser (expires after 15 min)
           
┌──────────────┐
│ Lock Released│
└──────────────┘
```

---

## File Structure

### Backend: `kindlife_app/api/row_locking.py`

**Lines:** 500  
**Created:** May 7, 2026

#### Key Classes

**`RowLockManager`**
- Manages all lock operations
- Uses `frappe.cache()` for Redis
- Handles TTL, heartbeat, session tracking

#### Key Methods

```python
# Lock Operations
acquire_lock(doc_name, row_idx, item_code) → {success, message, ...}
release_lock(doc_name, row_idx, force=False) → {success, message, ...}
get_all_locks(doc_name) → {row_idx: lock_data, ...}

# Heartbeat & Tracking
refresh_heartbeat(doc_name, row_idx) → {success, ttl_remaining}
get_active_users(doc_name) → [user_emails]
cleanup_user_locks(session_id) → count

# Internal Helpers
_get_lock_key(doc_name, row_idx) → "se_row_lock:{doc}:{idx}"
_get_lock_data(doc_name, row_idx) → lock_data or None
_set_lock_data(doc_name, row_idx, lock_data) → bool
```

#### Whitelisted APIs

```python
@frappe.whitelist()
def acquire_row_lock(stock_entry_name, row_idx, item_code=None)

@frappe.whitelist()
def release_row_lock(stock_entry_name, row_idx, force=False)

@frappe.whitelist()
def get_all_row_locks(stock_entry_name)

@frappe.whitelist()
def refresh_lock_heartbeat(stock_entry_name, row_idx)

@frappe.whitelist()
def get_active_users(stock_entry_name)

@frappe.whitelist()
def cleanup_my_locks()
```

---

### Frontend: `kindlife_app/public/js/stock_entry.js`

**Lines Added:** ~334 (908 → 1242 lines)  
**Modified:** May 7, 2026

#### Constructor Properties (NEW)

```javascript
// Row Locking
this.locked_rows = new Map();           // idx -> lock_data
this.current_locked_row = null;         // Currently locked row idx
this.heartbeat_interval = null;         // Heartbeat timer
this.lock_refresh_interval = null;      // Lock check timer
this.HEARTBEAT_FREQUENCY = 4 * 60 * 1000;    // 4 minutes
this.LOCK_CHECK_FREQUENCY = 30 * 1000;       // 30 seconds
```

#### CSS Styles (NEW)

```css
.grid-row.row-locked {
    background-color: #fff3cd !important;  /* Yellow */
    opacity: 0.75;
}

.grid-row.row-locked::before {
    content: "🔒";
}

.grid-row.row-locked-by-me {
    background-color: #d1ecf1 !important;  /* Blue */
    border-left: 3px solid #0c5460;
}

.grid-row.row-locked-by-me::before {
    content: "🔓";
}
```

#### Key Methods (NEW)

```javascript
// Lock Management
async load_row_locks()                    // Load all locks from Redis
async try_lock_row(row_idx, item_code)    // Acquire lock before scan
async release_lock(row_idx, force=false)  // Release specific lock
async release_all_my_locks()              // Release all user's locks

// Heartbeat & Polling
start_heartbeat()                         // Start heartbeat (4 min)
stop_heartbeat()                          // Stop heartbeat
start_lock_check()                        // Start polling (30 sec)
stop_lock_check()                         // Stop polling

// UI Updates
update_row_lock_ui()                      // Update visual indicators
async show_locked_rows()                  // Show lock management dialog

// Utilities
format_time(iso_string)                   // Format datetime
is_row_locked_by_other(row_idx)          // Check if blocked
```

#### Modified Methods

**`setup_scanner()`** - Added lock initialization
```javascript
async setup_scanner() {
    await this.load_local_serial_data();
    await this.load_row_locks();        // NEW
    this.start_lock_check();            // NEW
    this.frm.refresh_field('items');
}
```

**`process_serial_scan()`** - Added lock checking
```javascript
async process_serial_scan(scanned_value) {
    // ... existing validation ...
    
    // NEW: Check if row locked by another user
    if (this.is_row_locked_by_other(target_idx)) {
        // Show error and abort
        return;
    }
    
    // NEW: Try to acquire lock if not already held
    if (!is_my_lock) {
        const lock_acquired = await this.try_lock_row(target_idx, row.item_code);
        if (!lock_acquired) return;
    }
    
    // ... continue with scanning ...
}
```

**`add_scanning_buttons()`** - Added Row Locking dropdown
```javascript
// Row Locking Buttons (NEW)
if (!this.frm.is_new()) {
    this.frm.add_custom_button(__('Release All My Locks'), ...);
    this.frm.add_custom_button(__('Show Locked Rows'), ...);
    this.frm.add_custom_button(__('Refresh Lock Status'), ...);
}
```

---

## Redis Data Structures

### Lock Data Structure

```json
{
  "user": "user@example.com",
  "user_full_name": "John Doe",
  "locked_at": "2026-05-07T10:30:00.000Z",
  "session_id": "abc123def456...",
  "row_item_code": "ITEM-001",
  "lock_type": "scanning",
  "ttl_remaining": 900
}
```

### Redis Keys

```
se_row_lock:SE-00001:1
  → Lock for Stock Entry SE-00001, Row 1
  → TTL: 900 seconds (15 minutes)
  → Value: JSON lock data

se_active_users:SE-00001
  → Set of active users on SE-00001
  → TTL: 300 seconds (5 minutes)
  → Value: ["user1@example.com", "user2@example.com"]

se_user_session:abc123def456
  → User session tracking
  → TTL: 900 seconds (15 minutes)
  → Value: {"active_locks": [{"doc": "SE-00001", "row": 1}]}
```

---

## Configuration

### Timings

```javascript
// Frontend
HEARTBEAT_FREQUENCY = 4 * 60 * 1000      // 4 minutes (240 sec)
LOCK_CHECK_FREQUENCY = 30 * 1000         // 30 seconds

// Backend
lock_ttl = 900                            // 15 minutes (900 sec)
heartbeat_ttl = 300                       // 5 minutes (300 sec)
```

### Why These Values?

- **Lock TTL (15 min):** Long enough for scanning session, short enough to auto-recover
- **Heartbeat (4 min):** Frequent enough to prevent expiry, not too chatty
- **Lock Check (30 sec):** Balance between real-time updates and server load

---

## User Interface

### Visual Indicators

| State | Background | Icon | Border | Tooltip |
|-------|-----------|------|--------|---------|
| **Unlocked** | White | None | None | None |
| **Locked by me** | Light blue (#d1ecf1) | 🔓 | Blue left (3px) | "Locked by you at {time}" |
| **Locked by other** | Yellow (#fff3cd) | 🔒 | None | "Locked by {name} at {time}" |

### Buttons

**Location:** Stock Entry Form → Dropdowns

```
Row Locking ▼
├── Release All My Locks    → Bulk release all user's locks
├── Show Locked Rows        → Dialog with lock management
└── Refresh Lock Status     → Manual refresh from Redis
```

### "Show Locked Rows" Dialog

```
┌─────────────────────────────────────────────────────────┐
│ 🔒 Locked Rows (3)                          [Refresh]   │
├─────────────────────────────────────────────────────────┤
│ Row │ Item Code │ Locked By  │ Locked At │ TTL │ Action│
├─────────────────────────────────────────────────────────┤
│ 🔓 1│ ITEM-001  │ You        │ 10:30 AM  │ 12m │[Release]│
│ 🔒 2│ ITEM-002  │ John Doe   │ 10:25 AM  │ 7m  │   —   │
│ 🔓 3│ ITEM-003  │ You        │ 10:35 AM  │ 14m │[Release]│
└─────────────────────────────────────────────────────────┘
```

---

## API Reference

### Frontend → Backend Calls

```javascript
// Acquire lock
frappe.call({
    method: 'kindlife_app.api.row_locking.acquire_row_lock',
    args: {
        stock_entry_name: 'SE-00001',
        row_idx: 1,
        item_code: 'ITEM-001'
    }
});

// Release lock
frappe.call({
    method: 'kindlife_app.api.row_locking.release_row_lock',
    args: {
        stock_entry_name: 'SE-00001',
        row_idx: 1,
        force: false
    }
});

// Get all locks
frappe.call({
    method: 'kindlife_app.api.row_locking.get_all_row_locks',
    args: {
        stock_entry_name: 'SE-00001'
    }
});

// Heartbeat
frappe.call({
    method: 'kindlife_app.api.row_locking.refresh_lock_heartbeat',
    args: {
        stock_entry_name: 'SE-00001',
        row_idx: 1
    }
});

// Cleanup all locks
frappe.call({
    method: 'kindlife_app.api.row_locking.cleanup_my_locks'
});
```

---

## Common Scenarios

### Scenario 1: Single User Scanning

```
1. User A opens SE-00001
2. User A scans serial on Row 1
   → Lock acquired
   → Row turns blue
   → Heartbeat starts
3. User A continues scanning Row 1
   → Lock already held
   → No re-acquisition needed
4. User A scans serial on Row 2
   → New lock acquired on Row 2
   → Row 1 lock still active
5. User A finishes and closes browser
   → Locks expire after 15 minutes
```

### Scenario 2: Multi-User Conflict

```
1. User A opens SE-00001, scans on Row 1
   → Row 1 locked by User A
   
2. User B opens SE-00001 (30 sec later)
   → Sees Row 1 with yellow background + 🔒
   → Tooltip: "Locked by User A at 10:30 AM"
   
3. User B tries to scan on Row 1
   → Alert: "Row #1 is being scanned by User A"
   → Scan blocked
   
4. User B scans on Row 2 instead
   → Row 2 locked by User B
   → Works fine
   
5. User A sees Row 2 turn yellow (30 sec later)
   → Lock check detected User B's lock
```

### Scenario 3: Lock Expiry

```
1. User A scans on Row 1 at 10:00 AM
   → Lock acquired, TTL = 15 min
   
2. User A goes to lunch (browser open)
   → Heartbeat continues until 10:04, 10:08, 10:12
   
3. At 10:15 AM (15 min later)
   → Lock expires (TTL reached)
   → Redis automatically deletes key
   
4. User B tries to scan on Row 1 at 10:16 AM
   → Lock not found
   → Acquires new lock
   → Works fine
```

### Scenario 4: Manual Release

```
1. User A scans on Rows 1, 2, 3
   → All three rows locked
   
2. User A clicks "Show Locked Rows"
   → Dialog shows 3 locked rows
   
3. User A clicks [Release] on Row 1
   → Row 1 unlocked
   → Dialog refreshes, shows 2 locked rows
   
4. User A clicks "Release All My Locks"
   → Confirmation dialog
   → All locks released
   → Heartbeat stops
```

---

## Troubleshooting

### Issue: Locks not showing up

**Symptoms:** Rows don't turn blue/yellow after scanning

**Diagnosis:**
```javascript
// Browser console
console.log(cur_frm.serial_scanner.locked_rows);
// Should show Map with locked rows
```

**Solutions:**
1. Check Redis is running: `redis-cli ping` → Should return `PONG`
2. Check `frappe.cache()` is working:
   ```python
   # Frappe console
   frappe.cache().set_value("test", "value")
   print(frappe.cache().get_value("test"))
   ```
3. Hard refresh browser: `Ctrl+Shift+R`
4. Check console for errors

---

### Issue: Heartbeat not working

**Symptoms:** Locks expire even when user is active

**Diagnosis:**
```javascript
// Browser console - should see every 4 minutes
// "Heartbeat sent for row X"
```

**Solutions:**
1. Check `heartbeat_interval` is set:
   ```javascript
   console.log(cur_frm.serial_scanner.heartbeat_interval);
   // Should be a number (timer ID)
   ```
2. Check for JavaScript errors in console
3. Verify document is saved (not new)

---

### Issue: Lock check not updating

**Symptoms:** Don't see other users' locks appear

**Diagnosis:**
```javascript
// Browser console - should see every 30 seconds
// "Loaded X row locks"
```

**Solutions:**
1. Check `lock_refresh_interval` is set:
   ```javascript
   console.log(cur_frm.serial_scanner.lock_refresh_interval);
   ```
2. Manually refresh: Click "Refresh Lock Status" button
3. Check network tab for API calls to `get_all_row_locks`

---

### Issue: Can't release lock

**Symptoms:** Release button doesn't work

**Diagnosis:**
```javascript
// Try manual release
await cur_frm.serial_scanner.release_lock(1);
```

**Solutions:**
1. Check browser console for errors
2. Verify you own the lock (not someone else's)
3. Try "Release All My Locks" button
4. Wait 15 minutes for auto-expiry

---

### Issue: Multiple users can scan same row

**Symptoms:** Lock checking not working

**Diagnosis:**
```javascript
// Check if lock checking is in process_serial_scan
// Should see lock check before serial validation
```

**Solutions:**
1. Verify code changes were deployed: `bench build`
2. Hard refresh browser
3. Check `is_row_locked_by_other()` method exists
4. Check Redis keys: `redis-cli keys "se_row_lock:*"`

---

## Testing Guide

### Manual Testing Checklist

**Single User:**
- [ ] Open Stock Entry, scan serial → Row turns blue
- [ ] Console shows "Heartbeat started"
- [ ] Continue scanning same row → Works
- [ ] Scan different row → New lock acquired
- [ ] Click "Show Locked Rows" → See your locks
- [ ] Click [Release] → Lock released
- [ ] Click "Release All My Locks" → All locks released

**Multi-User (2 browsers):**
- [ ] User A scans Row 1 → Blue
- [ ] User B opens same doc → Row 1 yellow after 30 sec
- [ ] User B tries to scan Row 1 → Blocked with alert
- [ ] User B scans Row 2 → Works
- [ ] User A sees Row 2 yellow after 30 sec
- [ ] User A clicks "Show Locked Rows" → Sees both locks

**Lock Expiry:**
- [ ] User A scans Row 1
- [ ] User A closes browser
- [ ] Wait 15 minutes
- [ ] User B scans Row 1 → Works (lock expired)

**Manual Release:**
- [ ] User A scans multiple rows
- [ ] User A clicks "Show Locked Rows" → See all locks
- [ ] User A releases specific lock → Works
- [ ] User A releases all locks → All released

---

## Performance Considerations

### Redis Operations

**Per User Session:**
- Lock acquisition: 1 write + 2 reads
- Heartbeat: 1 write every 4 minutes
- Lock check: 1 read every 30 seconds
- Lock release: 1 delete + 1 read

**Estimated Load (10 concurrent users):**
- Writes: ~2.5 per minute (heartbeats)
- Reads: ~20 per minute (lock checks)
- Total: ~22.5 ops/min

**Conclusion:** Very lightweight, Redis can handle thousands of ops/sec

---

### Network Traffic

**Per User Session:**
- Initial load: 1 API call (get_all_locks)
- Lock acquisition: 1 API call per row
- Heartbeat: 1 API call every 4 minutes
- Lock check: 1 API call every 30 seconds

**Bandwidth:**
- Lock data: ~200 bytes per lock
- API overhead: ~500 bytes per call
- Total per user: ~1 KB/min

**Conclusion:** Negligible network impact

---

## Security Considerations

### Access Control

**Lock Ownership:**
- Users can only release their own locks
- System Managers can force-release any lock
- Session-based tracking prevents cross-session conflicts

**Force Release:**
```python
# Only System Managers can force-release
if force and "System Manager" not in frappe.get_roles():
    return {"success": False, "message": "Permission denied"}
```

### Data Validation

**Input Sanitization:**
- All inputs validated before Redis operations
- Row indices converted to integers
- Document names validated against database

**TTL Protection:**
- All locks have mandatory TTL (15 min)
- No permanent locks possible
- Auto-cleanup on expiry

---

## Future Enhancements

### Potential Improvements

1. **Auto-release on document close**
   ```javascript
   window.addEventListener('beforeunload', async () => {
       await cur_frm.serial_scanner.release_all_my_locks();
   });
   ```

2. **Real-time updates using Frappe Realtime**
   ```python
   # Backend: Publish lock changes
   frappe.publish_realtime(
       'row_lock_changed',
       {'doc': doc_name, 'row': row_idx, 'action': 'acquired'},
       doctype='Stock Entry',
       docname=doc_name
   )
   
   # Frontend: Subscribe to changes
   frappe.realtime.on('row_lock_changed', (data) => {
       this.load_row_locks();
   });
   ```

3. **Lock queue system**
   - Allow users to "request" a locked row
   - Notify lock owner when someone is waiting
   - Auto-transfer lock when released

4. **Lock analytics**
   - Track lock duration, conflicts, wait times
   - Identify bottlenecks in scanning workflow
   - Generate reports for optimization

5. **Configurable timings**
   - Allow admin to configure TTL, heartbeat, check frequency
   - Per-warehouse or per-user settings
   - Dynamic adjustment based on load

---

## Maintenance

### Monitoring

**Check Redis Health:**
```bash
redis-cli ping
redis-cli info stats
redis-cli keys "se_row_lock:*" | wc -l  # Count active locks
```

**Check Lock Status:**
```python
# Frappe console
from kindlife_app.api.row_locking import RowLockManager
manager = RowLockManager()
locks = manager.get_all_locks("SE-00001")
print(locks)
```

**Clear Stuck Locks:**
```python
# Frappe console - CAUTION: Clears all locks
cache = frappe.cache()
keys = cache.get_keys("se_row_lock:*")
for key in keys:
    cache.delete_value(key)
```

---

### Debugging

**Enable Verbose Logging:**
```javascript
// Browser console
cur_frm.serial_scanner.debug = true;  // Add this property for verbose logs
```

**Check Lock Data:**
```javascript
// Browser console
console.table(Array.from(cur_frm.serial_scanner.locked_rows.entries()));
```

**Test Lock Acquisition:**
```javascript
// Browser console
await cur_frm.serial_scanner.try_lock_row(1, 'ITEM-001');
```

---

## Related Documentation

- **Stock Entry Reference:** `.kiro/steering/stock-entry-reference.md`
- **Frappe-First Policy:** `.kiro/steering/frappe-first-policy.md`
- **Implementation Summary:** `ROW_LOCKING_IMPLEMENTATION_SUMMARY.md`
- **Manual Unlock Guide:** `MANUAL_UNLOCK_GUIDE.md`

---

## Changelog

### Version 1.0.0 (May 7, 2026)
- ✅ Initial implementation
- ✅ Redis-based locking with frappe.cache()
- ✅ 15-minute TTL with auto-expiry
- ✅ Heartbeat system (4 min)
- ✅ Lock checking (30 sec)
- ✅ Visual indicators (blue/yellow)
- ✅ Manual release buttons
- ✅ "Show Locked Rows" dialog
- ✅ "Release All My Locks" button
- ✅ Tested and working in production

---

## Contact & Support

**Implementation:** Kiro AI Assistant  
**Testing:** User (May 7, 2026)  
**Status:** ✅ Production Ready

**For Issues:**
1. Check troubleshooting section above
2. Review browser console for errors
3. Verify Redis is running
4. Check network tab for API failures

---

**Last Updated:** May 7, 2026  
**Version:** 1.0.0  
**Status:** Production
