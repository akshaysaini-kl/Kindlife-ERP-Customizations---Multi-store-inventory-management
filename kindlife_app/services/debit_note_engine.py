# debit_note_engine.py
# B2C Debit Note Automation for Kindlife
# Handles debit note generation for both brand-fulfilled and warehouse-fulfilled items.

import frappe
from frappe import _
from frappe.utils import flt, today, getdate, cint


def daily_debit_note_check():
    """
    Daily cron entry point.
    Checks if today matches the configured cron_run_day in Kindlife Settings.
    If so, runs the monthly debit note consolidation.
    """
    settings = frappe.get_single("Kindlife Settings")
    frappe.log_error(
        "monthly_cron_debit_note_generation={0}, cron_run_day={1}, today_day={2}".format(
            settings.monthly_cron_debit_note_generation,
            settings.cron_run_day,
            getdate(today()).day,
        ),
        "Debit Note Cron: daily check triggered",
    )

    if not settings.monthly_cron_debit_note_generation:
        return

    frappe.enqueue(
        "kindlife_app.services.debit_note_engine.generate_monthly_debit_notes",
        queue="long",
        timeout=3600,
    )


@frappe.whitelist()
def trigger_debit_note_generation():
    """
    Manual API to trigger debit note generation immediately (bypasses cron day check).
    Use from bench console or a button for testing.
    """
    frappe.enqueue(
        "kindlife_app.services.debit_note_engine.generate_monthly_debit_notes",
        queue="long",
        timeout=3600,
    )
    frappe.msgprint("Debit note generation queued in background.", alert=True)


def generate_monthly_debit_notes():
    """
    Consolidates uncovered SO lines per supplier and generates debit notes.
    Only processes SO items that have a B2C discount amount and
    have not yet been covered by a debit note.
    """
    # Get all submitted B2C SOs with uncovered B2C discount items
    uncovered_items = frappe.db.sql("""
        SELECT
            soi.name as so_item_name,
            soi.parent as sales_order,
            soi.item_code,
            soi.qty,
            soi.custom_b2c_discount_amount,
            soi.custom_fulfilled_by,
            soi.supplier,
            soi.purchase_order
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
            AND so.custom_type = 'B2C'
            AND soi.custom_b2c_discount_amount > 0
            AND soi.custom_debit_note_created = 0
            AND soi.delivered_by_supplier = 1
    """, as_dict=True)

    frappe.log_error(
        "Found {0} uncovered B2C SO items".format(len(uncovered_items)),
        "Debit Note Engine: generate_monthly_debit_notes",
    )

    if not uncovered_items:
        return

    # Group by supplier (one debit note per supplier)
    supplier_groups = {}
    for item in uncovered_items:
        supplier = item.supplier
        if not supplier:
            frappe.log_error(
                "SO Item {0} ({1}) has no supplier — skipping".format(
                    item.so_item_name, item.item_code
                ),
                "Debit Note Engine: missing supplier",
            )
            continue

        if supplier not in supplier_groups:
            supplier_groups[supplier] = []
        supplier_groups[supplier].append(item)

    # Generate one debit note per supplier
    for supplier, items in supplier_groups.items():
        try:
            create_debit_note_for_supplier(supplier, items)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Debit Note Generation Error for Supplier {0}".format(supplier),
            )


def create_debit_note_for_supplier(supplier, so_items):
    """
    Creates a Purchase Invoice (Debit Note / is_return=1) for the given supplier,
    covering the B2C discount amounts for all specified SO items.
    Only creates if a PO is present on the SO items; groups by PO.
    """
    from frappe.utils import now_datetime

    # Group items by PO — only process items that have a linked PO
    po_groups = {}
    no_po_items = []
    for so_item in so_items:
        po = so_item.get("purchase_order")
        if not po:
            no_po_items.append(so_item.so_item_name)
            continue
        if po not in po_groups:
            po_groups[po] = []
        po_groups[po].append(so_item)

    if no_po_items:
        frappe.log_error(
            "Skipped {0} SO items with no linked PO: {1}".format(len(no_po_items), no_po_items[:20]),
            "Debit Note Engine: no PO — skipped",
        )

    if not po_groups:
        return

    # Resolve company from first item's SO
    company = frappe.db.get_value("Sales Order", so_items[0].sales_order, "company")

    for po_name, items in po_groups.items():
        total_debit = sum(flt(i.custom_b2c_discount_amount) for i in items)
        if total_debit <= 0:
            continue

        supplier_price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")

        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = supplier
        pi.company = company
        pi.is_return = 1
        pi.custom_type = "B2C"
        pi.bill_no = "DN-B2C-{0}-{1}".format(po_name[:15], now_datetime().strftime("%Y%m%d%H%M%S"))
        pi.bill_date = today()
        pi.posting_date = today()
        pi.update_stock = 0
        if supplier_price_list:
            pi.buying_price_list = supplier_price_list

        for so_item in items:
            rate = flt(so_item.custom_b2c_discount_amount / so_item.qty) if so_item.qty else 0
            pi.append("items", {
                "item_code": so_item.item_code,
                "qty": -flt(so_item.qty),
                "rate": rate,
                "purchase_order": po_name,
            })

        pi.flags.ignore_permissions = True
        pi.flags.ignore_mandatory = True
        pi.insert()

        # Mark SO items as covered
        for so_item in items:
            frappe.db.set_value(
                "Sales Order Item",
                so_item.so_item_name,
                "custom_debit_note_created",
                1,
                update_modified=False,
            )

        frappe.db.commit()

        frappe.log_error(
            "Brand DN {0} created for PO {1}, Supplier {2}, total: {3}, items: {4}".format(
                pi.name, po_name, supplier, total_debit, len(items)
            ),
            "Debit Note Created",
        )



@frappe.whitelist()
def generate_debit_note_for_brand_fulfilled(po_name):
    """
    Manual trigger: Generate one Debit Note per PO for uncovered SO lines.
    Only picks up SO line items not yet covered by a prior debit note.
    """
    # Get uncovered SO items linked to this PO
    uncovered_items = frappe.db.sql("""
        SELECT
            soi.name as so_item_name,
            soi.parent as sales_order,
            soi.item_code,
            soi.qty,
            soi.custom_b2c_discount_amount
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
            AND soi.purchase_order = %s
            AND soi.custom_b2c_discount_amount > 0
            AND soi.custom_debit_note_created = 0
    """, po_name, as_dict=True)

    if not uncovered_items:
        frappe.msgprint(_("No uncovered B2C items found for PO {0}.").format(po_name))
        return

    create_debit_note_for_po(po_name, uncovered_items)
    frappe.msgprint(_("Debit Note created for PO {0}.").format(po_name), alert=True)


def trace_po_from_serial_no(serial_no):
    """
    Trace a serial number to its Purchase Order.
    Serial No → purchase_document_no (Purchase Receipt) → PR Item → PO.
    Returns the Purchase Order name if found, otherwise None.
    """
    # Get the Purchase Receipt from Serial No's purchase_document_no
    purchase_receipt = frappe.db.get_value("Serial No", serial_no, "purchase_document_no")
    if not purchase_receipt:
        return None

    # Verify it's actually a Purchase Receipt (not a Stock Entry etc.)
    if not frappe.db.exists("Purchase Receipt", purchase_receipt):
        return None

    frappe.log_error("purchase_receipt={0} for serial_no={1}".format(purchase_receipt, serial_no), "Warehouse DN: trace_po_from_serial_no")
    # Get the PO from the Purchase Receipt Item that has this serial no
    # First try via Serial and Batch Bundle on PR Items
    po = frappe.db.sql("""
        SELECT pri.purchase_order
        FROM `tabPurchase Receipt Item` pri
        WHERE pri.parent = %s
            AND pri.item_code = (SELECT item_code FROM `tabSerial No` WHERE name = %s)
            AND pri.purchase_order IS NOT NULL
            AND pri.purchase_order != ''
        LIMIT 1
    """, (purchase_receipt, serial_no), as_dict=True)

    frappe.log_error("po={0} for PR={1}, serial_no={2}".format(po, purchase_receipt, serial_no), "Warehouse DN: PO lookup result")
    if po:
        return po[0].purchase_order

    return None


# ───────────────────────────────────────────────────────────────────
#  Warehouse-Fulfilled Debit Note Cron
# ───────────────────────────────────────────────────────────────────

def daily_warehouse_debit_note_check():
    """
    Daily cron for warehouse-fulfilled debit notes.
    Runs when monthly_cron_debit_note_generation is enabled in Kindlife Settings.
    """
    settings = frappe.get_single("Kindlife Settings")

    if not settings.monthly_cron_debit_note_generation:
        return

    frappe.enqueue(
        "kindlife_app.services.debit_note_engine.generate_warehouse_debit_notes",
        queue="long",
        timeout=3600,
    )


def generate_warehouse_debit_notes():
    """
    Find uncovered warehouse-fulfilled B2C SO items, trace their serial numbers
    back to Purchase Orders, and generate debit notes grouped by PO.
    """
    # 1. Find uncovered warehouse-fulfilled SO items with discount amounts
    uncovered_items = frappe.db.sql("""
        SELECT
            soi.name as so_item_name,
            soi.parent as sales_order,
            soi.item_code,
            soi.qty,
            soi.custom_b2c_discount_amount
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
            AND so.custom_type = 'B2C'
            AND soi.delivered_by_supplier = 0
            AND soi.custom_b2c_discount_amount > 0
            AND soi.custom_debit_note_created = 0
    """, as_dict=True)

    frappe.log_error(
        "Found {0} uncovered warehouse-fulfilled SO items".format(len(uncovered_items)),
        "Warehouse Debit Note: generate started",
    )

    if not uncovered_items:
        return

    # 2. For each SO item, trace serial numbers → PR → PO
    po_groups = {}  # {po_name: [so_item_dicts]}
    skipped = []

    for item in uncovered_items:
        po_name = trace_po_for_so_item(item.so_item_name, item.item_code)

        if not po_name:
            skipped.append(item.so_item_name)
            continue

        # Store the traced PO on the item dict for later use
        item["traced_po"] = po_name

        if po_name not in po_groups:
            po_groups[po_name] = []
        po_groups[po_name].append(item)

    if skipped:
        frappe.log_error(
            "Skipped {0} items (no PO found): {1}".format(len(skipped), skipped[:20]),
            "Warehouse Debit Note: items skipped",
        )

    # 3. Generate one debit note per PO
    for po_name, items in po_groups.items():
        try:
            create_warehouse_debit_note(po_name, items)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Warehouse Debit Note Error for PO {0}".format(po_name),
            )


def trace_po_for_so_item(so_item_name, item_code):
    """
    Trace from SO Item → Pick List Item → Serial/Batch Bundle → Serial No → PR → PO.
    Returns the first PO found, or None.
    """
    # Get Pick List Items linked to this SO Item
    pick_list_items = frappe.db.get_all(
        "Pick List Item",
        filters={
            "sales_order_item": so_item_name,
        },
        fields=["serial_and_batch_bundle", "serial_no"],
    )

    if not pick_list_items:
        return None

    for pli in pick_list_items:
        serial_nos = []

        # Method 1: Serial and Batch Bundle (modern ERPNext)
        if pli.serial_and_batch_bundle:
            bundle_entries = frappe.db.get_all(
                "Serial and Batch Entry",
                filters={"parent": pli.serial_and_batch_bundle},
                fields=["serial_no"],
            )
            serial_nos.extend([e.serial_no for e in bundle_entries if e.serial_no])

        # Method 2: Legacy serial_no field (newline-separated)
        if not serial_nos and pli.serial_no:
            serial_nos = [s.strip() for s in pli.serial_no.split("\n") if s.strip()]

        # Trace each serial number to find a PO
        for sn in serial_nos:
            po = trace_po_from_serial_no(sn)
            if po:
                return po

    return None


def create_warehouse_debit_note(po_name, so_items):
    """
    Creates a Purchase Invoice (Debit Note) for warehouse-fulfilled items
    linked to the given PO.
    """
    from frappe.utils import now_datetime

    total_debit = sum(flt(i.custom_b2c_discount_amount) for i in so_items)
    if total_debit <= 0:
        return

    po_doc = frappe.get_doc("Purchase Order", po_name)

    supplier_price_list = frappe.db.get_value("Supplier", po_doc.supplier, "default_price_list")

    pi = frappe.new_doc("Purchase Invoice")
    pi.supplier = po_doc.supplier
    pi.company = po_doc.company
    pi.is_return = 1
    pi.custom_type = "B2C"
    pi.bill_no = "DN-WH-{0}-{1}".format(po_name[:15], now_datetime().strftime("%Y%m%d%H%M%S"))
    pi.bill_date = today()
    pi.posting_date = today()
    pi.update_stock = 0
    if supplier_price_list:
        pi.buying_price_list = supplier_price_list

    for so_item in so_items:
        rate = flt(so_item.custom_b2c_discount_amount / so_item.qty) if so_item.qty else 0
        pi.append("items", {
            "item_code": so_item.item_code,
            "qty": -flt(so_item.qty),
            "rate": rate,
            "purchase_order": po_name,
        })

    pi.flags.ignore_permissions = True
    pi.flags.ignore_mandatory = True
    pi.insert()

    # Mark SO items as covered
    for so_item in so_items:
        frappe.db.set_value(
            "Sales Order Item",
            so_item.so_item_name,
            "custom_debit_note_created",
            1,
            update_modified=False,
        )

    frappe.db.commit()

    frappe.log_error(
        "Warehouse Debit Note {0} created for PO {1}, supplier {2}, total: {3}, items: {4}".format(
            pi.name, po_name, po_doc.supplier, total_debit, len(so_items)
        ),
        "Warehouse Debit Note Created",
    )

