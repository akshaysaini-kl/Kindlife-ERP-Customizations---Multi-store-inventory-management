import frappe

class PurchaseReturnService:
    def __init__(self, source_pr_name):
        self.source_pr = source_pr_name
        self.pr_items = self._get_pr_items()
        self.bundles = self._get_bundles()
        self.active_serials = self._fetch_active_serials()

    def _get_pr_items(self):
        return frappe.get_all("Purchase Receipt Item", 
            filters={"parent": self.source_pr},
            fields=["name", "item_code", "item_name", "rate", "uom", "stock_uom", 
                    "conversion_factor", "serial_and_batch_bundle", 
                    "rejected_serial_and_batch_bundle"]
        )

    def _get_bundles(self):
        """Map Bundle IDs to their Origin (Accepted vs Rejected)"""
        bundle_map = {}
        all_bundles = []
        
        for row in self.pr_items:
            if row.serial_and_batch_bundle:
                bundle_map[row.serial_and_batch_bundle] = {"is_rejected": False, "pr_item": row}
                all_bundles.append(row.serial_and_batch_bundle)
            
            if row.rejected_serial_and_batch_bundle:
                bundle_map[row.rejected_serial_and_batch_bundle] = {"is_rejected": True, "pr_item": row}
                all_bundles.append(row.rejected_serial_and_batch_bundle)
        
        return {"map": bundle_map, "ids": all_bundles}

    def _fetch_active_serials(self):
        """
        1. Fetch all serials linked to PR Bundles.
        2. Filter only those that are currently ACTIVE in DB.
        3. Return detailed dict.
        """
        if not self.bundles['ids']:
            return {}

        # 1. Get Links (Bundle <-> Serial)
        entries = frappe.get_all("Serial and Batch Entry",
            filters={"parent": ["in", self.bundles['ids']]},
            fields=["parent", "serial_no"]
        )
        
        if not entries: 
            return {}

        serial_nos = [e.serial_no for e in entries if e.serial_no]

        # 2. Get Live Status (Warehouse, Batch, Status)
        # Optimization: Fetch only necessary fields
        live_serials = frappe.get_all("Serial No",
            filters={"name": ["in", serial_nos], "status": "Active"},
            fields=["name", "item_code", "warehouse", "batch_no", "custom_barcode"]
        )
        
        # Map for fast access
        live_map = {s.name: s for s in live_serials}
        
        results = {}
        for entry in entries:
            # Only include if serial is still Active
            if entry.serial_no in live_map:
                s_doc = live_map[entry.serial_no]
                bundle_info = self.bundles['map'].get(entry.parent)
                
                # Construct the data object
                results[entry.serial_no] = {
                    "serial_no": s_doc.name,
                    "item_code": s_doc.item_code,
                    "warehouse": s_doc.warehouse,
                    "batch_no": s_doc.batch_no,
                    "custom_barcode": s_doc.custom_barcode,
                    # Origin Context
                    "is_rejected_origin": bundle_info["is_rejected"],
                    "pr_item_row": bundle_info["pr_item"]
                }
        return results

    def get_grouped_data(self):
        """
        Groups all active serials by [Item + Warehouse + Batch + PR_Row].
        Returns a dictionary keyed by a unique grouping string.
        """
        groups = {}

        for serial_data in self.active_serials.values():
            pr_item = serial_data['pr_item_row']
            
            # UNIQUE KEY GENERATION
            # Format: Item::Warehouse::Batch::PR_Row_Name
            group_key = f"{serial_data['item_code']}::{serial_data['warehouse']}::{serial_data['batch_no']}::{pr_item.name}"

            if group_key not in groups:
                groups[group_key] = {
                    "key": group_key,
                    "item_code": serial_data['item_code'],
                    "item_name": pr_item.item_name,
                    "warehouse": serial_data['warehouse'],
                    "batch_no": serial_data['batch_no'],
                    "pr_item_name": pr_item.name,
                    "is_rejected_origin": serial_data['is_rejected_origin'],
                    
                    # Row data from PR
                    "rate": pr_item.rate,
                    "uom": pr_item.uom,
                    "stock_uom": pr_item.stock_uom,
                    "conversion_factor": pr_item.conversion_factor,
                    
                    # Accumulators
                    "serials": []
                }
            
            groups[group_key]["serials"].append(serial_data["serial_no"])
        # Sort values by Item Code, then Batch No
        sorted_list = sorted(
            groups.values(), 
            key=lambda x: (x['item_code'], x['batch_no'])
        )

        # Reconstruct Dictionary in Sorted Order
        # This ensures both Python Loop and JS Cache receive items in order
        sorted_groups = {item['key']: item for item in sorted_list}

        return sorted_groups


    def get_scanner_map(self):
            """
            Returns lightweight map for Frontend Scanner:
            { "SERIAL_NO": { "key": "...", "serial": "..." } }
            """
            scan_map = {}
            for s in self.active_serials.values():
                pr_item_name = s['pr_item_row'].name
                # 1. Create the Group Key
                key = f"{s['item_code']}::{s['warehouse']}::{s['batch_no']}::{pr_item_name}"
                
                # 2. Create the Value Object
                val = {"key": key, "serial": s['serial_no']}

                # 3. Assign to Map
                scan_map[s['serial_no']] = val
                if s.get('custom_barcode'):
                    scan_map[s['custom_barcode']] = val
                    
            return scan_map
