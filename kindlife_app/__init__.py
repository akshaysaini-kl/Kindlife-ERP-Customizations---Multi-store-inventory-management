__version__ = "0.0.1"

# my_custom_app/__init__.py
import india_compliance
import erpnext.stock.doctype.pick_list.pick_list
import erpnext.stock.get_item_details
import erpnext.stock.stock_ledger
from .monkey_patches.item_price_override import get_item_price as custom_get_item_price, get_price_list_rate as custom_get_price_list_rate ,get_price_list_rate_for as custom_get_price_list_rate_for
from kindlife_app.custom_scripts.purchase_order import make_purchase_invoice

# Fill values in received column
import erpnext.buying.doctype.purchase_order.purchase_order
from .monkey_patches.purchase_order_override import make_purchase_receipt as override_make_purchase_receipt

# Remove QI check
import erpnext.controllers.stock_controller
from .monkey_patches.stock_controller_override import overrideStockController 

# Remove check for Accepted != 0 
import erpnext.buying.utils
import erpnext.controllers.buying_controller
from .monkey_patches.utils_override import validate_for_items as override_validate_for_items

from .monkey_patches.accounts_controller_override import AccountsController as override_AccountsController
import erpnext.controllers.accounts_controller

# AccountsController
import erpnext.stock.serial_batch_bundle
from .monkey_patches.serial_batch_bundle_override import SerialBatchCreation as overrideSerialBatchCreation, SerialBatchBundle as overrideSerialBatchBundle

#pick list
from .monkey_patches.pick_list_override import get_available_item_locations_for_batched_item, set_item_locations_with_warning

from .monkey_patches.stock_ledger import update_entries_after_overrides

# e waybill
from .monkey_patches.ewaybill_override import set_party_address_details as override_set_party_address_details


import erpnext.controllers.sales_and_purchase_return#.validate_quantity
from .monkey_patches.sales_and_purchase_return import patched_validate_quantity


def override_methods():
    erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice = make_purchase_invoice
    erpnext.stock.get_item_details.get_item_price = custom_get_item_price
    erpnext.stock.get_item_details.get_price_list_rate_for = custom_get_price_list_rate_for
    erpnext.stock.get_item_details.get_price_list_rate = custom_get_price_list_rate
    # Fill barcode values
    erpnext.stock.serial_batch_bundle.SerialBatchCreation.set_attr = overrideSerialBatchCreation.set_attr
    erpnext.stock.serial_batch_bundle.SerialBatchCreation.get_auto_created_serial_nos = overrideSerialBatchCreation.get_auto_created_serial_nos
    erpnext.stock.serial_batch_bundle.SerialBatchCreation.make_serial_and_batch_bundle = overrideSerialBatchCreation.make_serial_and_batch_bundle
    erpnext.stock.serial_batch_bundle.SerialBatchCreation.set_serial_batch_entries_for_purchase_receipt = overrideSerialBatchCreation.set_serial_batch_entries_for_purchase_receipt
    erpnext.stock.serial_batch_bundle.SerialBatchCreation.create_batch = overrideSerialBatchCreation.create_batch
    # erpnext.stock.serial_batch_bundle.SerialBatchCreation.set_serial_batch_entries = overrideSerialBatchCreation.set_serial_batch_entries
    # erpnext.stock.serial_batch_bundle.SerialBatchCreation.set_auto_serial_batch_entries_for_inward = overrideSerialBatchCreation.set_auto_serial_batch_entries_for_inward
    # erpnext.stock.serial_batch_bundle.SerialBatchCreation.set_auto_serial_batch_entries_for_outward = overrideSerialBatchCreation.set_auto_serial_batch_entries_for_outward
    # erpnext.stock.serial_batch_bundle.SerialBatchCreation.add_serial_nos_for_batch_item = overrideSerialBatchCreation.add_serial_nos_for_batch_item
    # erpnext.stock.serial_batch_bundle.SerialBatchCreation.make_serial_and_batch_bundle = overrideSerialBatchCreation.make_serial_and_batch_bundle
    # erpnext.stock.serial_batch_bundle.SerialBatchBundle.validate_item_and_warehouse = overrideSerialBatchBundle.validate_item_and_warehouse
    erpnext.stock.serial_batch_bundle.SerialBatchBundle.update_serial_no_status_warehouse = overrideSerialBatchBundle.update_serial_no_status_warehouse
    
    erpnext.stock.serial_batch_bundle.SerialBatchBundle.make_serial_batch_no_bundle = overrideSerialBatchBundle.make_serial_batch_no_bundle
    erpnext.stock.serial_batch_bundle.SerialBatchBundle.post_process = overrideSerialBatchBundle.post_process
    # Fill custom_received column in PR
    erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt = override_make_purchase_receipt
    # Remove QI check
    # erpnext.controllers.stock_controller.StockController = overrideStockController
    # erpnext.controllers.stock_controller.StockController.create_serial_batch_bundle = overrideStockController.create_serial_batch_bundle
    # erpnext.controllers.stock_controller.StockController._create_serial_batch_bundle_sync = overrideStockController._create_serial_batch_bundle_sync
    # erpnext.controllers.stock_controller.StockController._create_serial_batch_bundle_async = overrideStockController._create_serial_batch_bundle_async
    # erpnext.controllers.stock_controller.StockController._create_placeholder_bundle = overrideStockController._create_placeholder_bundle
    # erpnext.controllers.stock_controller.StockController._create_placeholder_entries = overrideStockController._create_placeholder_entries
    erpnext.controllers.stock_controller.StockController.validate_inspection = overrideStockController.validate_inspection
    # erpnext.controllers.stock_controller.StockController.update_bundle_details = overrideStockController.update_bundle_details
    erpnext.controllers.stock_controller.StockController.make_bundle_using_old_serial_batch_fields = overrideStockController.make_bundle_using_old_serial_batch_fields

    # Remove check for Accepted!=0
    # The validate_for_items function is imported in the file, so PR gets this before we override it.
    # So here I have overriden it directly in the file as well
    erpnext.buying.utils.validate_for_items = override_validate_for_items
    erpnext.controllers.buying_controller.validate_for_items = override_validate_for_items
    erpnext.controllers.accounts_controller.AccountsController.validate_qty_is_not_zero = override_AccountsController.validate_qty_is_not_zero

    erpnext.stock.doctype.pick_list.pick_list.get_available_item_locations_for_batched_item = get_available_item_locations_for_batched_item
    
    # Override set_item_locations to show warnings for removed/reduced items
    erpnext.stock.doctype.pick_list.pick_list.PickList.set_item_locations = set_item_locations_with_warning

    # erpnext.stock.stock_ledger.update_entries_after.calculate_valuation_for_serial_batch_bundle = update_entries_after_overrides.calculate_valuation_for_serial_batch_bundle

    india_compliance.gst_india.utils.e_waybill.EWaybillData.set_party_address_details = override_set_party_address_details

    erpnext.controllers.sales_and_purchase_return.validate_quantity = patched_validate_quantity

override_methods()