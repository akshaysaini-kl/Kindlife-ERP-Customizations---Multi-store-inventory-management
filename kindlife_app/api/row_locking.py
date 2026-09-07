"""
Row-Level Locking System for Stock Entry
Uses Redis (via frappe.cache()) for fast, temporary locks with auto-expiry.

Author: Development Team
Created: 2026-05-07
Version: 1.0.0
"""

import frappe
import json
from datetime import datetime
from typing import Dict, Optional, List


class RowLockManager:
    """
    Generic row-level lock manager using Redis (frappe.cache()).
    Pure Redis implementation - no database writes for locks.
    
    Works for any doctype with child table rows (Stock Entry, Pick List, etc.)
    
    Features:
    - Auto-expiring locks (15 min TTL)
    - Heartbeat system to keep locks alive
    - Force-release for System Managers
    - Session tracking for cleanup
    - Independent lock namespaces per doctype
    - Smart merge for conflict resolution
    """
    
    def __init__(self, key_prefix="row_lock", doctype=None, child_table=None, 
                 scanned_serial_field=None, scanned_qty_field=None):
        """
        Initialize generic row lock manager.
        
        Args:
            key_prefix: Redis key prefix for lock namespace (e.g., "se_row_lock", "pl_row_lock")
            doctype: DocType name (e.g., "Stock Entry", "Pick List")
            child_table: Child table field name (e.g., "items", "locations")
            scanned_serial_field: Field name for scanned serials (e.g., "custom_scanned_serial_no", "serial_no")
            scanned_qty_field: Field name for scanned quantity (e.g., "custom_scanned_qty", "picked_qty")
        """
        self.cache = frappe.cache()
        self.lock_ttl = 900  # 15 minutes
        self.heartbeat_ttl = 300  # 5 minutes for active users
        self.key_prefix = key_prefix
        self.doctype = doctype
        self.child_table = child_table
        self.scanned_serial_field = scanned_serial_field
        self.scanned_qty_field = scanned_qty_field
    
    def _get_lock_key(self, doc_name: str, row_idx: int) -> str:
        """Generate Redis key for row lock."""
        return f"{self.key_prefix}:{doc_name}:{row_idx}"
    
    def _get_active_users_key(self, doc_name: str) -> str:
        """Generate Redis key for active users set."""
        return f"{self.key_prefix}_active_users:{doc_name}"
    
    def _get_user_session_key(self, session_id: str) -> str:
        """Generate Redis key for user session tracking."""
        return f"{self.key_prefix}_user_session:{session_id}"
    
    def _get_lock_data(self, doc_name: str, row_idx: int) -> Optional[Dict]:
        """
        Get lock data from Redis.
        
        Returns:
            Dict with lock info or None if not locked
        """
        lock_key = self._get_lock_key(doc_name, row_idx)
        lock_json = self.cache.get_value(lock_key)
        
        if lock_json:
            try:
                return json.loads(lock_json)
            except json.JSONDecodeError:
                # Corrupted data, delete it
                self.cache.delete_value(lock_key)
                frappe.log_error(
                    f"Corrupted lock data for {lock_key}",
                    "Row Lock Data Error"
                )
                return None
        return None
    
    def _set_lock_data(self, doc_name: str, row_idx: int, lock_data: Dict) -> bool:
        """
        Set lock data in Redis with TTL.
        
        Returns:
            True if successful, False otherwise
        """
        lock_key = self._get_lock_key(doc_name, row_idx)
        lock_json = json.dumps(lock_data)
        
        try:
            self.cache.set_value(lock_key, lock_json, expires_in_sec=self.lock_ttl)
            return True
        except Exception as e:
            frappe.log_error(
                f"Failed to set lock for {lock_key}: {str(e)}",
                "Row Lock Set Error"
            )
            return False
    
    def acquire_lock(self, doc_name: str, row_idx: int, item_code: str = None) -> Dict:
        """
        Try to acquire lock on a row.
        
        Args:
            doc_name: Stock Entry name
            row_idx: Row index (integer)
            item_code: Optional item code for display
        
        Returns:
            {
                "success": bool,
                "message": str,
                "locked_by": str (if failed),
                "locked_at": str (if failed),
                "ttl_remaining": int (seconds remaining on lock),
                "is_refresh": bool (if this was a refresh)
            }
        """
        user = frappe.session.user
        session_id = frappe.session.sid
        
        # Check existing lock
        existing_lock = self._get_lock_data(doc_name, row_idx)
        
        if existing_lock:
            # Same user re-acquiring (refresh)
            if existing_lock['user'] == user:
                # Refresh TTL
                self._set_lock_data(doc_name, row_idx, existing_lock)
                
                return {
                    "success": True,
                    "message": "Lock refreshed",
                    "is_refresh": True
                }
            
            # Locked by someone else
            lock_key = self._get_lock_key(doc_name, row_idx)
            ttl = self.cache.ttl(lock_key) or 0
            
            return {
                "success": False,
                "message": f"Row is being scanned by {existing_lock['user_full_name']}",
                "locked_by": existing_lock['user_full_name'],
                "locked_by_email": existing_lock['user'],
                "locked_at": existing_lock['locked_at'],
                "ttl_remaining": ttl,
                "item_code": existing_lock.get('row_item_code')
            }
        
        # Acquire new lock
        lock_data = {
            "user": user,
            "user_full_name": frappe.get_value("User", user, "full_name") or user,
            "locked_at": datetime.now().isoformat(),
            "session_id": session_id,
            "row_item_code": item_code,
            "lock_type": "scanning"
        }
        
        success = self._set_lock_data(doc_name, row_idx, lock_data)
        
        if success:
            # Track active user
            self._add_active_user(doc_name, user)
            
            # Track in user session
            self._track_user_lock(session_id, doc_name, row_idx)
            
            return {
                "success": True,
                "message": "Lock acquired successfully",
                "is_refresh": False
            }
        else:
            return {
                "success": False,
                "message": "Failed to acquire lock (Redis error)"
            }
    
    def release_lock(self, doc_name: str, row_idx: int, force: bool = False) -> Dict:
        """
        Release lock on a row.
        
        Args:
            doc_name: Stock Entry name
            row_idx: Row index
            force: If True, allows System Manager to force-release
        
        Returns:
            {
                "success": bool,
                "message": str,
                "was_forced": bool (if force-released by admin)
            }
        """
        user = frappe.session.user
        existing_lock = self._get_lock_data(doc_name, row_idx)
        
        if not existing_lock:
            return {
                "success": True,
                "message": "No lock found (already released or expired)"
            }
        
        # Check permission
        can_release = (
            existing_lock['user'] == user or  # Owner
            (force and "System Manager" in frappe.get_roles())  # Force by admin
        )
        
        if not can_release:
            return {
                "success": False,
                "message": f"Cannot release lock owned by {existing_lock['user_full_name']}"
            }
        
        # Delete lock
        lock_key = self._get_lock_key(doc_name, row_idx)
        self.cache.delete_value(lock_key)
        
        # Remove from user session tracking
        self._untrack_user_lock(existing_lock['session_id'], doc_name, row_idx)
        
        return {
            "success": True,
            "message": "Lock released successfully",
            "was_forced": force and existing_lock['user'] != user
        }
    
    def get_all_locks(self, doc_name: str) -> Dict[int, Dict]:
        """
        Get all locked rows for a document.
        
        Args:
            doc_name: Document name
        
        Returns:
            {
                row_idx: {lock_data with ttl_remaining},
                ...
            }
        """
        # Get document to know row count
        if not self.doctype or not self.child_table:
            return {}
        
        try:
            doc = frappe.get_doc(self.doctype, doc_name)
        except frappe.DoesNotExistError:
            return {}
        
        locks = {}
        
        # Get child table items dynamically
        child_items = getattr(doc, self.child_table, [])
        
        for item in child_items:
            lock_data = self._get_lock_data(doc_name, item.idx)
            if lock_data:
                # Add TTL info
                lock_key = self._get_lock_key(doc_name, item.idx)
                lock_data['ttl_remaining'] = self.cache.ttl(lock_key) or 0
                locks[item.idx] = lock_data
        
        return locks
    
    def refresh_heartbeat(self, doc_name: str, row_idx: int) -> Dict:
        """
        Refresh lock TTL (heartbeat from frontend).
        
        Args:
            doc_name: Stock Entry name
            row_idx: Row index
        
        Returns:
            {
                "success": bool,
                "message": str,
                "ttl_remaining": int (seconds)
            }
        """
        user = frappe.session.user
        existing_lock = self._get_lock_data(doc_name, row_idx)
        
        if not existing_lock:
            return {
                "success": False,
                "message": "Lock not found or expired"
            }
        
        # Only owner can refresh
        if existing_lock['user'] != user:
            return {
                "success": False,
                "message": "Cannot refresh lock owned by another user"
            }
        
        # Refresh TTL
        self._set_lock_data(doc_name, row_idx, existing_lock)
        
        # Refresh active user
        self._add_active_user(doc_name, user)
        
        lock_key = self._get_lock_key(doc_name, row_idx)
        ttl = self.cache.ttl(lock_key) or 0
        
        return {
            "success": True,
            "message": "Heartbeat received",
            "ttl_remaining": ttl
        }
    
    def get_active_users(self, doc_name: str) -> List[str]:
        """
        Get list of users currently active on this document.
        
        Args:
            doc_name: Stock Entry name
        
        Returns:
            List of user emails
        """
        key = self._get_active_users_key(doc_name)
        users_json = self.cache.get_value(key)
        
        if users_json:
            try:
                return json.loads(users_json)
            except json.JSONDecodeError:
                return []
        return []
    
    def _add_active_user(self, doc_name: str, user: str):
        """Add user to active users set."""
        key = self._get_active_users_key(doc_name)
        users = set(self.get_active_users(doc_name))
        users.add(user)
        
        self.cache.set_value(
            key,
            json.dumps(list(users)),
            expires_in_sec=self.heartbeat_ttl
        )
    
    def _track_user_lock(self, session_id: str, doc_name: str, row_idx: int):
        """Track lock in user session (for cleanup on logout)."""
        key = self._get_user_session_key(session_id)
        session_json = self.cache.get_value(key)
        
        if session_json:
            try:
                session_data = json.loads(session_json)
            except json.JSONDecodeError:
                session_data = {"active_locks": []}
        else:
            session_data = {"active_locks": []}
        
        # Add lock
        lock_ref = {"doc": doc_name, "row": row_idx}
        if lock_ref not in session_data['active_locks']:
            session_data['active_locks'].append(lock_ref)
        
        self.cache.set_value(
            key,
            json.dumps(session_data),
            expires_in_sec=self.lock_ttl
        )
    
    def _untrack_user_lock(self, session_id: str, doc_name: str, row_idx: int):
        """Remove lock from user session tracking."""
        key = self._get_user_session_key(session_id)
        session_json = self.cache.get_value(key)
        
        if not session_json:
            return
        
        try:
            session_data = json.loads(session_json)
            lock_ref = {"doc": doc_name, "row": row_idx}
            
            if lock_ref in session_data['active_locks']:
                session_data['active_locks'].remove(lock_ref)
            
            self.cache.set_value(
                key,
                json.dumps(session_data),
                expires_in_sec=self.lock_ttl
            )
        except (json.JSONDecodeError, KeyError):
            pass
    
    def cleanup_user_locks(self, session_id: str) -> int:
        """
        Cleanup all locks for a user session (on logout).
        
        Args:
            session_id: User session ID
        
        Returns:
            Number of locks released
        """
        key = self._get_user_session_key(session_id)
        session_json = self.cache.get_value(key)
        
        if not session_json:
            return 0
        
        try:
            session_data = json.loads(session_json)
            count = 0
            
            for lock_ref in session_data['active_locks']:
                lock_key = self._get_lock_key(lock_ref['doc'], lock_ref['row'])
                self.cache.delete_value(lock_key)
                count += 1
            
            # Clear session data
            self.cache.delete_value(key)
            
            return count
        except (json.JSONDecodeError, KeyError):
            return 0
    
    def smart_merge_scanned_data(self, doc):
        """
        Smart merge scanned serial data when document was modified by another user.
        Combines scanned data from both the current document and the database version.
        
        Args:
            doc: Current document object (from user's form)
        
        Returns:
            Dict with merge statistics
        """
        if not self.scanned_serial_field or not self.scanned_qty_field:
            frappe.throw("Smart merge requires scanned_serial_field and scanned_qty_field configuration")
        
        # Get latest document from database
        try:
            latest_doc = frappe.get_doc(self.doctype, doc.name)
        except frappe.DoesNotExistError:
            # Document doesn't exist yet, no merge needed
            return {"merged": False, "reason": "Document doesn't exist in database"}
        
        # Get child table items
        current_items = getattr(doc, self.child_table, [])
        latest_items = getattr(latest_doc, self.child_table, [])
        
        merge_stats = {
            "merged": False,
            "rows_merged": 0,
            "serials_added": 0,
            "details": []
        }
        
        # Merge each row
                # Merge each row
        for current_row in current_items:
            # Check if row was intentionally cleared by user (using flags)
            # Flags are temporary and don't require DB changes
            cleared_rows = doc.flags.get('cleared_rows', [])
            if current_row.idx in cleared_rows:
                # User intentionally cleared this row - don't merge
                merge_stats["details"].append({
                    "row_idx": current_row.idx,
                    "item_code": getattr(current_row, 'item_code', 'Unknown'),
                    "action": "skipped",
                    "reason": "Row was intentionally cleared by user"
                })
                continue
            
            # Find corresponding row in latest document by idx
            latest_row = None
            for row in latest_items:
                if row.idx == current_row.idx:
                    latest_row = row
                    break
            
            if not latest_row:
                continue  # Row doesn't exist in DB version

            
            # Get serials from both versions
            current_serials_str = getattr(current_row, self.scanned_serial_field, '') or ''
            latest_serials_str = getattr(latest_row, self.scanned_serial_field, '') or ''
            
            # Parse into sets (automatically removes duplicates)
            current_serials = set(s.strip() for s in current_serials_str.split('\n') if s.strip())
            latest_serials = set(s.strip() for s in latest_serials_str.split('\n') if s.strip())
            
            # Check if merge is needed
            if current_serials == latest_serials:
                continue  # No difference, skip
            
            # Merge: Union of both sets
            merged_serials = current_serials | latest_serials
            
            # Count new serials added
            serials_from_current = len(current_serials - latest_serials)
            serials_from_latest = len(latest_serials - current_serials)
            
            if serials_from_current > 0 or serials_from_latest > 0:
                # Update current row with merged data
                setattr(current_row, self.scanned_serial_field, '\n'.join(sorted(merged_serials)))
                setattr(current_row, self.scanned_qty_field, len(merged_serials))
                
                merge_stats["merged"] = True
                merge_stats["rows_merged"] += 1
                merge_stats["serials_added"] += serials_from_latest
                merge_stats["details"].append({
                    "row_idx": current_row.idx,
                    "item_code": getattr(current_row, 'item_code', 'Unknown'),
                    "my_serials": serials_from_current,
                    "their_serials": serials_from_latest,
                    "total_serials": len(merged_serials)
                })
        
        # Update modified timestamp to match database (prevents "Document modified" error)
        doc.modified = latest_doc.modified
        
        return merge_stats


# ============================================
# Whitelisted API Methods (Generic for all doctypes)
# ============================================

# Configuration mapping for different doctypes
DOCTYPE_LOCK_CONFIG = {
    "Stock Entry": {
        "key_prefix": "se_row_lock",
        "child_table": "items",
        "name_prefix": "MAT-STE-",
        "scanned_serial_field": "custom_scanned_serial_no",
        "scanned_qty_field": "custom_scanned_qty"
    },
    "Pick List": {
        "key_prefix": "pl_row_lock",
        "child_table": "locations",
        "name_prefix": "STO-PICK-",
        "scanned_serial_field": "serial_no",
        "scanned_qty_field": "picked_qty"
    }
}

def _get_doctype_config(doc_name: str = None, doctype: str = None) -> Dict:
    """
    Get configuration for a doctype.
    Auto-detects doctype from doc_name if not provided.
    
    Args:
        doc_name: Document name (e.g., "SE-00001", "PL-00001", "MAT-STE-00236")
        doctype: DocType name (e.g., "Stock Entry", "Pick List")
    
    Returns:
        Dict with key_prefix, doctype, and child_table
    """
    # If doctype not provided, try to detect from doc_name
    if not doctype and doc_name:
        # First try prefix matching
        for dt, config in DOCTYPE_LOCK_CONFIG.items():
            if doc_name.startswith(config["name_prefix"]):
                doctype = dt
                break
        
        # If still not found, query database to get the actual doctype
        if not doctype:
            try:
                # Query the document to find its doctype
                # We need to check multiple possible doctypes
                for dt in DOCTYPE_LOCK_CONFIG.keys():
                    if frappe.db.exists(dt, doc_name):
                        doctype = dt
                        break
                
                if not doctype:
                    frappe.throw(f"Could not determine doctype for document: {doc_name}")
            except Exception as e:
                frappe.log_error(f"Error detecting doctype for {doc_name}: {str(e)}")
                frappe.throw(f"Could not determine doctype for document: {doc_name}")
    
    # Get configuration
    if doctype not in DOCTYPE_LOCK_CONFIG:
        frappe.throw(f"Row locking not configured for doctype: {doctype}")
    
    config = DOCTYPE_LOCK_CONFIG[doctype].copy()
    config["doctype"] = doctype
    return config


@frappe.whitelist()
def acquire_row_lock(doc_name, row_idx, item_code=None, doctype=None):
    """
    API: Try to acquire lock on a row (generic for any doctype).
    
    Args:
        doc_name: Document name (SE-00001, PL-00001, etc.)
        row_idx: Row index (integer)
        item_code: Optional item code for display
        doctype: Optional doctype name (auto-detected from doc_name if not provided)
    
    Returns:
        {success, message, locked_by, locked_at, ttl_remaining}
    """
    config = _get_doctype_config(doc_name, doctype)
    
    manager = RowLockManager(
        key_prefix=config["key_prefix"],
        doctype=config["doctype"],
        child_table=config["child_table"]
    )
    return manager.acquire_lock(doc_name, int(row_idx), item_code)


@frappe.whitelist()
def release_row_lock(doc_name, row_idx, force=False, doctype=None):
    """
    API: Release lock on a row (generic for any doctype).
    
    Args:
        doc_name: Document name (SE-00001, PL-00001, etc.)
        row_idx: Row index (integer)
        force: Force release (System Manager only)
        doctype: Optional doctype name (auto-detected from doc_name if not provided)
    
    Returns:
        {success, message, was_forced}
    """
    config = _get_doctype_config(doc_name, doctype)
    
    manager = RowLockManager(
        key_prefix=config["key_prefix"],
        doctype=config["doctype"],
        child_table=config["child_table"]
    )
    return manager.release_lock(doc_name, int(row_idx), bool(force))


@frappe.whitelist()
def get_all_row_locks(doc_name, doctype=None):
    """
    API: Get all locked rows for a document (generic for any doctype).
    
    Args:
        doc_name: Document name (SE-00001, PL-00001, etc.)
        doctype: Optional doctype name (auto-detected from doc_name if not provided)
    
    Returns:
        {
            row_idx: {user, locked_at, ttl_remaining, ...},
            ...
        }
    """
    config = _get_doctype_config(doc_name, doctype)
    
    manager = RowLockManager(
        key_prefix=config["key_prefix"],
        doctype=config["doctype"],
        child_table=config["child_table"]
    )
    return manager.get_all_locks(doc_name)


@frappe.whitelist()
def refresh_lock_heartbeat(doc_name, row_idx, doctype=None):
    """
    API: Refresh lock TTL (heartbeat) - generic for any doctype.
    
    Args:
        doc_name: Document name (SE-00001, PL-00001, etc.)
        row_idx: Row index (integer)
        doctype: Optional doctype name (auto-detected from doc_name if not provided)
    
    Returns:
        {success, message, ttl_remaining}
    """
    config = _get_doctype_config(doc_name, doctype)
    
    manager = RowLockManager(
        key_prefix=config["key_prefix"],
        doctype=config["doctype"],
        child_table=config["child_table"]
    )
    return manager.refresh_heartbeat(doc_name, int(row_idx))


@frappe.whitelist()
def get_active_users(doc_name, doctype=None):
    """
    API: Get list of users currently active on document (generic for any doctype).
    
    Args:
        doc_name: Document name (SE-00001, PL-00001, etc.)
        doctype: Optional doctype name (auto-detected from doc_name if not provided)
    
    Returns:
        [user_email, ...]
    """
    config = _get_doctype_config(doc_name, doctype)
    
    manager = RowLockManager(
        key_prefix=config["key_prefix"],
        doctype=config["doctype"],
        child_table=config["child_table"]
    )
    return manager.get_active_users(doc_name)


@frappe.whitelist()
def cleanup_my_locks(doctype=None):
    """
    API: Cleanup all locks for current user session (generic for any doctype).
    
    Args:
        doctype: Optional doctype name (if not provided, cleans all configured doctypes)
    
    Returns:
        {success, count, message}
    """
    total_count = 0
    
    if doctype:
        # Clean specific doctype
        config = _get_doctype_config(None, doctype)
        manager = RowLockManager(
            key_prefix=config["key_prefix"],
            doctype=config["doctype"],
            child_table=config["child_table"]
        )
        total_count = manager.cleanup_user_locks(frappe.session.sid)
    else:
        # Clean all configured doctypes
        for dt in DOCTYPE_LOCK_CONFIG.keys():
            config = DOCTYPE_LOCK_CONFIG[dt]
            manager = RowLockManager(
                key_prefix=config["key_prefix"],
                doctype=dt,
                child_table=config["child_table"]
            )
            total_count += manager.cleanup_user_locks(frappe.session.sid)
    
    return {
        "success": True,
        "count": total_count,
        "message": f"Released {total_count} lock(s)"
    }
