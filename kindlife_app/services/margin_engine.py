# margin_engine.py
# B2C Margin Calculation Engine for Kindlife
# Runs on SO validate and on-demand via "Recalculate Margins" button.

import frappe
from frappe import _
from frappe.utils import flt, getdate


def on_sales_order_submit(doc, method):
    """Hook: automatically run margin engine when SO is validated/submitted."""
    run_margin_engine(doc)


@frappe.whitelist()
def recalculate_margins(sales_order_name):
    """
    Whitelisted API for the 'Recalculate Margins' button.
    Clears and rebuilds all B2C margin fields on a submitted SO.
    Uses db.set_value since the doc is already saved.
    """
    doc = frappe.get_doc("Sales Order", sales_order_name)
    for item in doc.items:
        try:
            result = compute_item_margin(item, doc.transaction_date)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                _("Margin Engine Error for {0} in {1}").format(item.item_code, sales_order_name)
            )
            result = None

        values = _get_margin_values(result)
        frappe.db.set_value(
            "Sales Order Item", item.name, values, update_modified=False
        )

    frappe.msgprint(_("B2C Margins recalculated successfully."), alert=True)


def recalculate_margins_bulk(so_names, brm_name):
    """
    Background job: recalculate margins for multiple submitted SOs.
    Called when a B2C Recurring Margin is submitted retroactively.
    Uses the BRM document directly to avoid re-querying the DB.
    """
    # Fetch the BRM entry data we already know about — no DB re-lookup race
    brm = frappe.db.get_value(
        "B2C Recurring Margin",
        brm_name,
        ["item_code", "supplier", "discount_pct", "cascading", "discount_application_order"],
        as_dict=True,
    )
    if not brm:
        frappe.log_error(
            "BRM {0} not found during bulk recalc".format(brm_name),
            "Margin Engine: BRM not found",
        )
        return

    for so_name in so_names:
        try:
            doc = frappe.get_doc("Sales Order", so_name)
            updated_count = 0
            for item in doc.items:
                # Only process the specific item+supplier this BRM covers
                if item.item_code != brm.item_code:
                    continue
                if item.get("supplier") != brm.supplier:
                    continue
                if not item.get("delivered_by_supplier"):
                    continue

                try:
                    result = compute_item_margin_with_entry(
                        item, doc.transaction_date, brm
                    )
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        "Margin Engine: compute failed for item {0} in SO {1}".format(
                            item.item_code, so_name
                        ),
                    )
                    result = None

                if result is None:
                    continue

                frappe.db.set_value(
                    "Sales Order Item",
                    item.name,
                    _get_margin_values(result),
                    update_modified=False,
                )
                updated_count += 1

            frappe.db.commit()
            frappe.log_error(
                "SO={0}: updated {1} item(s)".format(so_name, updated_count),
                "Margin Engine: Bulk recalc complete",
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Bulk Margin Recalc Error for SO {0}".format(so_name),
            )


def compute_item_margin_with_entry(item, transaction_date, brm):
    """
    Compute B2C margin using a pre-fetched BRM entry dict.
    Bypasses the DB lookup in resolve_b2c_margin_entry.
    """
    mrp, base_margin_pct = get_base_margin_from_item_price(item.item_code, brm.supplier)
    if not mrp:
        mrp = flt(item.custom_list_price)
    if not mrp:
        return None

    discount_pct = flt(brm.discount_pct)
    cascading = brm.cascading or ""
    discount_application_order = brm.discount_application_order or ""

    model_number, model_label = determine_margin_model(cascading, discount_application_order)
    qty = flt(item.qty) or 1

    if model_number == 1:
        result = calculate_margin_model_1(mrp, base_margin_pct, discount_pct, qty)
    elif model_number == 2:
        result = calculate_margin_model_2(mrp, base_margin_pct, discount_pct, qty)
    elif model_number == 3:
        result = calculate_margin_model_3(mrp, base_margin_pct, discount_pct, qty)
    else:
        return None

    result["margin_model"] = model_label
    result["discount_pct"] = discount_pct
    return result


def run_margin_engine(doc):
    """
    Main entry point. Sets margin fields directly on the doc's item objects
    so they are saved as part of the current transaction (works during validate).
    Accepts a Sales Order doc object.
    """
    for item in doc.items:
        try:
            result = compute_item_margin(item, doc.transaction_date)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                _("Margin Engine Error for {0} in {1}").format(item.item_code, doc.name)
            )
            result = None

        values = _get_margin_values(result)
        # Set values directly on the item object (in-memory)
        for field, value in values.items():
            item.set(field, value)


def _get_margin_values(result):
    """Return a dict of field values from the computation result, or zeroed-out defaults."""
    if result:
        return {
            "custom_b2c_discount_pct": result["discount_pct"],
            "custom_margin_model": result["margin_model"],
            "custom_b2c_discount_amount": result["discount_amount"],
            "custom_effective_margin_pct": result["effective_margin_pct"],
            "custom_effective_margin_amount": result["effective_margin_amount"],
        }
    return {
        "custom_b2c_discount_pct": 0,
        "custom_margin_model": "",
        "custom_b2c_discount_amount": 0,
        "custom_effective_margin_pct": 0,
        "custom_effective_margin_amount": 0,
    }


def compute_item_margin(item, transaction_date):
    """
    Compute B2C margin for a single SO Item.
    Handles both brand-fulfilled and warehouse-fulfilled items.
    - Brand items: supplier from item.supplier
    - Warehouse items: supplier from Item Supplier child table
    Returns a dict with all computed fields, or None if data is insufficient.
    """
    # 1. Resolve supplier based on fulfillment type
    if item.get("delivered_by_supplier"):
        # Brand-fulfilled: supplier is on the SO Item
        supplier = item.get("supplier")
    else:
        # Warehouse-fulfilled: resolve supplier from Item Supplier child table
        supplier = frappe.db.get_value(
            "Item Supplier",
            {"parent": item.item_code, "parenttype": "Item"},
            "supplier",
            order_by="idx asc",
        )

    if not supplier:
        return None

    # 2. Get MRP and Base Margin from Item Price (supplier's price list)
    mrp, base_margin_pct = get_base_margin_from_item_price(item.item_code, supplier)
    if not mrp:
        # Fallback to the MRP already on the SO Item
        mrp = flt(item.custom_list_price)
    if not mrp:
        return None

    # 3. Resolve B2C discount AND margin model from B2C Recurring Margin entry
    margin_entry = resolve_b2c_margin_entry(item.item_code, supplier, transaction_date)
    if not margin_entry:
        return None

    discount_pct = flt(margin_entry.discount_pct)
    cascading = margin_entry.cascading or ""
    discount_application_order = margin_entry.discount_application_order or ""

    # 4. Determine margin model from the B2C Recurring Margin entry flags
    model_number, model_label = determine_margin_model(cascading, discount_application_order)
    qty = flt(item.qty) or 1

    # 5. Calculate based on model
    if model_number == 1:
        result = calculate_margin_model_1(mrp, base_margin_pct, discount_pct, qty)
    elif model_number == 2:
        result = calculate_margin_model_2(mrp, base_margin_pct, discount_pct, qty)
    elif model_number == 3:
        result = calculate_margin_model_3(mrp, base_margin_pct, discount_pct, qty)
    else:
        return None

    result["margin_model"] = model_label
    result["discount_pct"] = discount_pct
    return result


def get_base_margin_from_item_price(item_code, supplier):
    """
    Fetch MRP (custom_buying_price) and Base Margin % (custom_margin)
    from the Item Price record on the supplier's buying price list.
    Returns (mrp, base_margin_pct) tuple.
    """
    # Get the supplier's default price list
    default_price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")

    if not default_price_list:
        return 0, 0

    # Find the active Item Price for this item on the supplier's price list
    item_price = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item_code,
            "price_list": default_price_list,
            "docstatus": ["!=", 2],
        },
        ["custom_buying_price", "custom_margin"],
        as_dict=True,
        order_by="valid_from desc",
    )

    if item_price:
        return flt(item_price.custom_buying_price), flt(item_price.custom_margin)

    return 0, 0


def resolve_b2c_margin_entry(item_code, supplier, transaction_date):
    """
    Find the active (submitted) B2C Recurring Margin entry whose date range
    covers the given transaction_date for the item+supplier combination.
    Returns the full entry (discount_pct, cascading, discount_application_order)
    or None if no matching entry.
    """
    transaction_date = getdate(transaction_date)

    entry = frappe.db.get_value(
        "B2C Recurring Margin",
        {
            "item_code": item_code,
            "supplier": supplier,
            "docstatus": 1,
            "start_date": ["<=", transaction_date],
            "end_date": [">=", transaction_date],
        },
        ["discount_pct", "cascading", "discount_application_order"],
        as_dict=True,
    )
    frappe.log_error(
        "Margin Engine: No margin result (item skipped): {0}".format(entry),
        "Margin Engine: No margin result (item skipped)",
    )
    return entry


def determine_margin_model(cascading, discount_application_order):
    """
    Determine margin model from cascading flags (sourced from B2C Recurring Margin).
    Returns (model_number, model_label) tuple.
    """
    if not cascading or cascading == "No":
        return 1, "Model 1 — Additive"
    elif cascading == "Yes" and discount_application_order == "Margin First":
        return 2, "Model 2 — Cascading, Margin First"
    elif cascading == "Yes" and discount_application_order == "Discount First":
        return 3, "Model 3 — Cascading, Discount First"
    else:
        return 1, "Model 1 — Additive"


def calculate_margin_model_1(mrp, base_margin_pct, discount_pct, qty):
    """
    Model 1 — Additive (Simple). Cascading = No.
    Both base margin and discount calculated independently on MRP, then summed.

    Example (MRP=100, Base Margin=30%, Discount=10%):
        Base Margin Amount = 100 * 30% = 30
        Discount Amount = 100 * 10% = 10
        Effective Margin = 30 + 10 = 40 → 40% of MRP
    """
    base_margin_amount = flt(mrp * base_margin_pct / 100)
    discount_amount = flt(mrp * discount_pct / 100)
    effective_margin_amount = base_margin_amount + discount_amount
    effective_margin_pct = flt(effective_margin_amount / mrp * 100) if mrp else 0

    return {
        "discount_amount": flt(discount_amount * qty, 2),
        "effective_margin_pct": flt(effective_margin_pct, 2),
        "effective_margin_amount": flt(effective_margin_amount * qty, 2),
    }


def calculate_margin_model_2(mrp, base_margin_pct, discount_pct, qty):
    """
    Model 2 — Cascading, Margin First.
    Base margin deducted from MRP first, then discount applied to net price.

    Example (MRP=100, Base Margin=30%, Discount=10%):
        Net Price After Margin = 100 * 70% = 70
        Discount Amount = 70 * 10% = 7
        Effective Margin = 30 + 7 = 37 → 37% of MRP
    """
    base_margin_amount = flt(mrp * base_margin_pct / 100)
    net_price_after_margin = mrp - base_margin_amount
    discount_amount = flt(net_price_after_margin * discount_pct / 100)
    effective_margin_amount = base_margin_amount + discount_amount
    effective_margin_pct = flt(effective_margin_amount / mrp * 100) if mrp else 0

    return {
        "discount_amount": flt(discount_amount * qty, 2),
        "effective_margin_pct": flt(effective_margin_pct, 2),
        "effective_margin_amount": flt(effective_margin_amount * qty, 2),
    }


def calculate_margin_model_3(mrp, base_margin_pct, discount_pct, qty):
    """
    Model 3 — Cascading, Discount First.
    Discount applied to MRP first, then base margin on the lower net price.

    Example (MRP=100, Base Margin=30%, Discount=10%):
        Net Price After Discount = 100 * 90% = 90
        Base Margin Amount = 90 * 30% = 27
        Effective Margin = 10 + 27 = 37 → 37% of MRP
    """
    discount_amount = flt(mrp * discount_pct / 100)
    net_price_after_discount = mrp - discount_amount
    base_margin_amount = flt(net_price_after_discount * base_margin_pct / 100)
    effective_margin_amount = discount_amount + base_margin_amount
    effective_margin_pct = flt(effective_margin_amount / mrp * 100) if mrp else 0

    return {
        "discount_amount": flt(discount_amount * qty, 2),
        "effective_margin_pct": flt(effective_margin_pct, 2),
        "effective_margin_amount": flt(effective_margin_amount * qty, 2),
    }
