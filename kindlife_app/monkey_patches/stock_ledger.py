from erpnext.stock.stock_ledger import update_entries_after
import frappe
from erpnext.stock.valuation import FIFOValuation, LIFOValuation, round_off_if_near_zero
from frappe.utils import flt



class update_entries_after_overrides(update_entries_after):
    def calculate_valuation_for_serial_batch_bundle(self, sle):
        if not frappe.db.exists("Serial and Batch Bundle", sle.serial_and_batch_bundle):
            return

        if not sle.auto_created_serial_and_batch_bundle or sle.actual_qty < 0:
            if self.args.get("sle_id") and sle.actual_qty < 0:
                doc = frappe.db.get_value(
                    "Serial and Batch Bundle",
                    sle.serial_and_batch_bundle,
                    ["total_amount", "total_qty"],
                    as_dict=1,
                )
            else:
                doc = frappe.get_doc("Serial and Batch Bundle", sle.serial_and_batch_bundle)
                doc.set_incoming_rate(save=True, allow_negative_stock=self.allow_negative_stock)
                doc.calculate_qty_and_amount(save=True)

        else:
            doc = frappe.db.get_value(
                "Serial and Batch Bundle",
                sle.serial_and_batch_bundle,
                ["total_amount", "total_qty"],
                as_dict=1,
            )

        self.wh_data.stock_value = round_off_if_near_zero(self.wh_data.stock_value + doc.total_amount)
        self.wh_data.qty_after_transaction += flt(doc.total_qty, self.flt_precision)
        if flt(self.wh_data.qty_after_transaction, self.flt_precision):
            self.wh_data.valuation_rate = flt(self.wh_data.stock_value, self.flt_precision) / flt(
                self.wh_data.qty_after_transaction, self.flt_precision
            )