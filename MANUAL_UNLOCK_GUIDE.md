# Manual Unlock Guide

## 🔓 How to Manually Unlock Rows

I've added 3 new buttons under the **"Row Locking"** dropdown menu in Stock Entry.

---

## Method 1: Using UI Buttons (Recommended)

### **Button 1: "Show Locked Rows"**

Shows a dialog with all currently locked rows with Release buttons.

### **Button 2: "Release All My Locks"**

Releases ALL locks you currently hold on this document.

### **Button 3: "Refresh Lock Status"**

Manually refreshes the lock status from Redis.

---

## Method 2: Using Browser Console (Advanced)

```javascript
// Release lock on Row 1
await cur_frm.serial_scanner.release_lock(1);

// Release all your locks
frappe.call({
    method: 'kindlife_app.api.row_locking.cleanup_my_locks',
    callback: (r) => {
        console.log(r.message);
        cur_frm.serial_scanner.load_row_locks();
    }
});
```

---

## To See Changes

```bash
cd ~/ERP/frappe-bench
bench build
bench restart
```

Then hard refresh browser: `Ctrl+Shift+R` or `Cmd+Shift+R`
