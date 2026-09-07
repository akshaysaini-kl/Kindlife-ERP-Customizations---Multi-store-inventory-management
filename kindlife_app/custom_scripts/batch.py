# custom_batch.py

import frappe

def autoname_batch(doc, method):
    if not doc.custom_batch_no:
        frappe.throw("Please enter Batch Code")

    # Get all existing batches with same custom_batch_no but different item
    existing_batches = frappe.get_all(
        "Batch",
        filters={"custom_batch_no": doc.custom_batch_no},
        fields=["batch_id", "item"]
    )
    print("existing_batches",existing_batches)
    same_item_exists = any(batch["item"] == doc.item for batch in existing_batches)

    if not existing_batches or same_item_exists:
        # First time or same item, use custom_batch_no as is
        doc.batch_id = doc.custom_batch_no
    else:
        print("in else")
        # Find max suffix
        counter = 1
        existing_names = [b["batch_id"] for b in existing_batches]
        while f"{doc.custom_batch_no}_{counter}" in existing_names:
            counter += 1
        doc.batch_id = f"{doc.custom_batch_no}_{counter}"
