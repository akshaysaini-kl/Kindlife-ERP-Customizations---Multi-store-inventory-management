import frappe
from frappe.utils import now
from frappe import _, bold
from frappe.model.naming import make_autoname
from frappe.model.naming import NamingSeries, parse_naming_series
from frappe.query_builder.functions import CombineDatetime, Sum, Timestamp
from frappe.utils import add_days, cint, cstr, flt, get_link_to_form, now, nowtime, today

from erpnext.stock.serial_batch_bundle import SerialBatchCreation as originalSerialBatchCreation, SerialBatchBundle as originalSerialBatchBundle,get_serial_nos_batch


from frappe.utils.background_jobs import enqueue
import barcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Image, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
import os
import tempfile
from io import BytesIO
import base64
from frappe.query_builder.functions import Concat


class SerialBatchCreation(originalSerialBatchCreation):
	def set_attr(self, key, value):
		setattr(self, key, value)
		self.__dict__[key] = value

	def get_auto_created_serial_nos(self):
		sr_nos = []
		serial_nos_details = []

		if not self.serial_no_series:
			msg = f"Please set Serial No Series in the item {self.item_code} or create Serial and Batch Bundle manually."
			frappe.throw(_(msg))

		voucher_no = ""
		if self.get("voucher_no"):
			voucher_no = self.get("voucher_no")
		
		obj = NamingSeries(self.serial_no_series)
		current_value = obj.get_current_value()

		def get_series(partial_series, digits):
			return f"{current_value:0{digits}d}"

		self.has_auto_created_serial_and_batch = True

		for _i in range(abs(cint(self.actual_qty))):
			current_value += 1

			serial_no = parse_naming_series(self.serial_no_series, number_generator=get_series)
			sr_nos.append(serial_no)
			serial_nos_details.append(
				(
					serial_no,
					serial_no,
					now(),
					now(),
					frappe.session.user,
					frappe.session.user,
					self.warehouse,
					self.company,
					self.item_code,
					self.item_name,
					self.description,
					"Active",
					voucher_no,
					self.batch_no,
				)
			)

		if serial_nos_details:
			fields = [
				"name",
				"serial_no",
				"creation",
				"modified",
				"owner",
				"modified_by",
				"warehouse",
				"company",
				"item_code",
				"item_name",
				"description",
				"status",
				"purchase_document_no",
				"batch_no",
			]

			frappe.db.bulk_insert("Serial No", fields=fields, values=set(serial_nos_details))
		obj.update_counter(current_value)
		return sr_nos

	# Commented in init
	def set_auto_serial_batch_entries_for_inward(self):
		if (self.get("batches") and self.has_batch_no) or (self.get("serial_nos") and self.has_serial_no):
			if self.use_serial_batch_fields and self.get("serial_nos"):
				print("Inside the Second if statement")
				self.make_serial_no_if_not_exists()
			print("Inside the first if statement")
			return
		
		self.batch_no = None
		if self.has_batch_no:
			self.batch_no = self.create_batch()


		# Dont run this for PR as we dont want serial no to be made there
		print("self.voucher_type --> ",self.voucher_type)
		if self.voucher_type == "Purchase Receipt":
			print("Skipped")
			return
		print("Not skipped __----_____---")

		if self.has_serial_no:
			print("Overriden set_auto_serial_batch_entries_for_inward_________________")
			self.serial_nos = self.get_auto_created_serial_nos()
		else:
			self.batches = frappe._dict({self.batch_no: abs(self.actual_qty)})


	# Commented in init
	def set_auto_serial_batch_entries_for_outward(self):
		from erpnext.stock.doctype.batch.batch import get_available_batches
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos_for_outward
		# self.batch_no = None
		# if self.has_batch_no:
		# 	self.batch_no = self.create_batch()
		if not self.has_batch_no:
			self.batch_no = None

		if (self.voucher_type == "Stock Entry" or self.get("reference_purchase_receipt") or True) and (self.has_batch_no): 
			if self.has_serial_no:
				print("Overriden set_auto_serial_batch_entries_for_outward -______________________---------------------")
				self.serial_nos = self.get_auto_created_serial_nos()
			else:
				self.batches = frappe._dict({self.batch_no: abs(self.actual_qty)})
			
			return

		kwargs = frappe._dict(
			{
				"item_code": self.item_code,
				"warehouse": self.warehouse,
				"qty": abs(self.actual_qty) if self.actual_qty else 0,
				"based_on": frappe.db.get_single_value("Stock Settings", "pick_serial_and_batch_based_on"),
			}
		)

		if self.get("ignore_serial_nos"):
			kwargs["ignore_serial_nos"] = self.ignore_serial_nos

		if (
			self.has_serial_no
			and self.has_batch_no
			and not self.get("serial_nos")
			and self.get("batches")
			and len(self.get("batches")) == 1
		):
			# If only one batch is available and no serial no is available
			kwargs["batches"] = next(iter(self.get("batches").keys()))
			self.serial_nos = get_serial_nos_for_outward(kwargs)

		elif self.has_serial_no and not self.get("serial_nos"):
			self.serial_nos = get_serial_nos_for_outward(kwargs)

		elif not self.has_serial_no and self.has_batch_no and not self.get("batches"):
			if self.get("posting_date"):
				kwargs["posting_date"] = self.get("posting_date")
				kwargs["posting_time"] = self.get("posting_time")
			self.batches = get_available_batches(kwargs)

	# Commented in init
	def add_serial_nos_for_batch_item(self):
		print("self.voucher_type == Purchase Receipt", self.voucher_type == "Purchase Receipt")
		print("Overriden add_serial_nos_for_batch_item")
		if not (self.has_serial_no and self.has_batch_no) or self.voucher_type == "Purchase Receipt":
			return

		if not self.get("serial_nos") and self.get("batches"):
			batches = list(self.get("batches").keys())
			if len(batches) == 1:
				self.batch_no = batches[0]
				print("original add_serial_nos_for_batch_item +++++++++++++++++++++++++++")
				self.serial_nos = self.get_auto_created_serial_nos()


	def make_serial_and_batch_bundle(self):
		doc = frappe.new_doc("Serial and Batch Bundle")
		valid_columns = doc.meta.get_valid_columns()
		for key, value in self.__dict__.items():
			if key in valid_columns:
				doc.set(key, value)
		
		self.set_attr("has_auto_created_serial_and_batch", False)

		if self.type_of_transaction == "Outward":
			self.set_auto_serial_batch_entries_for_outward()
		elif self.type_of_transaction == "Inward":
			self.set_auto_serial_batch_entries_for_inward()
			self.add_serial_nos_for_batch_item()

		if hasattr(self, "via_landed_cost_voucher") and self.via_landed_cost_voucher:
			doc.flags.via_landed_cost_voucher = self.via_landed_cost_voucher

		print(self.get("has_auto_created_serial_and_batch"))
		print(self.get("sle"))
		print(self.get("voucher_type"))
		# print(self.sle.actual_qty)
		# print(is_internal_supplier(self.sle.voucher_type, self.sle.voucher_no))
		if (
			self.get("sle")
			and self.get("has_auto_created_serial_and_batch")
			and self.sle.voucher_type in ["Purchase Receipt", "Purchase Invoice"]
			and self.sle.actual_qty > 0
			and not is_internal_supplier(self.sle.voucher_type, self.sle.voucher_no)
		):
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_validate = True
			doc.save()
			print("set_serial_batch_entries_for_purchase_receipt")
			self.set_serial_batch_entries_for_purchase_receipt(doc)
			return doc
		elif self.get("voucher_type") and self.get("voucher_type")=="Pick List":
			self.set_serial_batch_entries(doc)
		else:
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_validate = True
			doc.save()
			print("else set_serial_batch_entries_for_purchase_receipt")
			self.set_serial_batch_entries_for_purchase_receipt(doc)
			return doc
			# self.set_serial_batch_entries(doc)
		if not doc.get("entries"):
			return frappe._dict({})

		if doc.voucher_no and frappe.get_cached_value(doc.voucher_type, doc.voucher_no, "docstatus") == 2:
			doc.voucher_no = ""

		doc.flags.ignore_validate_serial_batch = False
		if self.get("make_bundle_from_sle") and self.type_of_transaction == "Inward":
			doc.flags.ignore_validate_serial_batch = True

		if not hasattr(self, "do_not_submit") or not self.do_not_submit:
			doc.flags.ignore_voucher_validation = True
			if self.get("sle"):
				doc.flags.ignore_validate = True
				doc.save()
				self.sle.db_set("serial_and_batch_bundle", doc.name, update_modified=False)

			if doc.flags.ignore_validate:
				doc.flags.ignore_validate = False

			doc.submit()
		else:
			doc.save()

		self.validate_qty(doc)

		return doc

	def set_serial_batch_entries_for_purchase_receipt(self, doc):
		incoming_rate = flt(self.get("incoming_rate"))

		precision = frappe.get_precision("Serial and Batch Entry", "qty")
		values = []
		fields = []
		total_amount = 0
		total_qty = 0
		if self.get("serial_nos"):
			fields = [
				"serial_no",
				"qty",
				"batch_no",
				"incoming_rate",
				"stock_value_difference",
				"parent",
				"parentfield",
				"parenttype",
				"idx",
				"creation",
				"modified",
				"owner",
				"modified_by",
				"name",
				"docstatus",
				"warehouse",
			]
			serial_no_wise_batch = frappe._dict({})
			if self.has_batch_no:
				serial_no_wise_batch = get_serial_nos_batch(self.serial_nos)

			qty = -1 if self.type_of_transaction == "Outward" else 1
			for index, serial_no in enumerate(self.serial_nos):
				if self.get("serial_nos_valuation"):
					incoming_rate = flt(self.get("serial_nos_valuation").get(serial_no))

				total_amount += flt(incoming_rate) * flt(qty)
				values.append(
					(
						serial_no,
						qty,
						serial_no_wise_batch.get(serial_no) or self.get("batch_no"),
						incoming_rate,
						flt(incoming_rate) * qty,
						doc.name,
						"entries",
						"Serial and Batch Bundle",
						index + 1,
						now(),
						now(),
						frappe.session.user,
						frappe.session.user,
						frappe.generate_hash(length=15),
						1,
						self.warehouse,
					)
				)

			total_qty = len(self.serial_nos)

		elif self.get("batches"):
			fields = [
				"batch_no",
				"qty",
				"incoming_rate",
				"stock_value_difference",
				"parent",
				"parentfield",
				"parenttype",
				"idx",
				"creation",
				"modified",
				"owner",
				"modified_by",
				"name",
				"docstatus",
				"warehouse",
			]

			for batch_no, batch_qty in self.batches.items():
				if self.get("batches_valuation"):
					incoming_rate = flt(self.get("batches_valuation").get(batch_no))

				qty = flt(batch_qty, precision) * (-1 if self.type_of_transaction == "Outward" else 1)
				total_qty += qty
				total_amount += flt(incoming_rate) * qty
				values.append(
					(
						batch_no,
						qty,
						incoming_rate,
						flt(incoming_rate) * flt(qty, precision),
						doc.name,
						"entries",
						"Serial and Batch Bundle",
						len(values) + 1,
						now(),
						now(),
						frappe.session.user,
						frappe.session.user,
						frappe.generate_hash(length=15),
						1,
						self.warehouse,
					)
				)
		print("values",values)
		OPTIMAL_BATCH_SIZE = 5000
		if fields and values:
			for i in range(0, len(values), OPTIMAL_BATCH_SIZE):
				chunk = values[i : i + OPTIMAL_BATCH_SIZE]
				frappe.db.bulk_insert("Serial and Batch Entry", fields=fields, values=chunk)

			# frappe.db.bulk_insert("Serial and Batch Entry", fields=fields, values=values)

		avg_rate = 0
		if total_qty and total_amount:
			avg_rate = flt(total_amount) / flt(total_qty)

		doc.db_set(
			{
				"docstatus": 1,
				"total_amount": total_amount,
				"avg_rate": avg_rate,
				"total_qty": total_qty,
			}
		)

		doc.reload()
	
	# Commented in init
	def set_serial_batch_entries(self, doc):
		from frappe.utils import flt

		incoming_rate = flt(self.get("incoming_rate"))
		precision = frappe.get_precision("Serial and Batch Entry", "qty")

		values = []  # will hold tuples
		idx = 1

		if self.get("serial_nos"):
			serial_no_wise_batch = frappe._dict({})
			if self.has_batch_no:
				serial_no_wise_batch = get_serial_nos_batch(self.serial_nos)

			qty = -1 if self.type_of_transaction == "Outward" else 1
			rate = frappe.db.get_value("Purchase Receipt Item", doc.voucher_detail_no, 'valuation_rate')
			# print("rate",rate)
			print("doc.warehouse",doc.warehouse)
			for serial_no in self.serial_nos:
				
				
				# if self.get("serial_nos_valuation"):
				incoming_rate = flt(rate)
				stock_value_difference = flt(qty) * incoming_rate
				# print("incoming_rate",incoming_rate)
				# print("stock_value_difference",stock_value_difference)
				serial_batch_entry_name = make_autoname("hash", "Serial and Batch Entry")
				values.append((
					serial_batch_entry_name,      # name (primary key)
					doc.name,                             # parent
					"entries",                            # parentfield
					"Serial and Batch Bundle",            # parenttype
					serial_no,
					qty,
					serial_no_wise_batch.get(serial_no) or self.get("batch_no"),
					doc.warehouse,
					incoming_rate,
					stock_value_difference,
					idx,
				))
				idx += 1

		elif self.get("batches"):
			for batch_no, batch_qty in self.batches.items():
				if self.get("batches_valuation"):
					incoming_rate = flt(self.get("batches_valuation").get(batch_no))
				serial_batch_entry_name = make_autoname("hash", "Serial and Batch Entry")

				values.append((
					serial_batch_entry_name,
					doc.name,
					"entries",
					"Serial and Batch Bundle",
					None,  # serial_no not applicable
					flt(batch_qty, precision) * (-1 if self.type_of_transaction == "Outward" else 1),
					batch_no,
					doc.warehouse,
					incoming_rate,
					idx,
				))
				idx += 1

		# 🚀 Bulk insert in one query
		if values:
			fields = [
				"name",
				"parent",
				"parentfield",
				"parenttype",
				"serial_no",
				"qty",
				"batch_no",
				"warehouse",
				"incoming_rate",
				"stock_value_difference",
				"idx",
			]
			print("bulk inserting rows")
			frappe.db.bulk_insert("Serial and Batch Entry", fields=fields, values=values)

			# Sync with in-memory doc object for downstream logic
			doc.set("entries", [dict(zip(fields, v)) for v in values])

	def create_batch(self):
		from erpnext.stock.doctype.batch.batch import make_batch

		if self.is_rejected:
			bundle = frappe.db.get_value(
				"Serial and Batch Bundle",
				{
					"voucher_no": self.voucher_no,
					"voucher_type": self.voucher_type,
					"voucher_detail_no": self.voucher_detail_no,
					"is_rejected": 0,
					"docstatus": 1,
					"is_cancelled": 0,
				},
				"name",
			)

			if bundle:
				if batch_no := frappe.db.get_value("Serial and Batch Entry", {"parent": bundle}, "batch_no"):
					return batch_no
		self.has_auto_created_serial_and_batch = True

		return make_batch(
			frappe._dict(
				{
					"item": self.get("item_code"),
					"reference_doctype": self.get("voucher_type"),
					"reference_name": self.get("voucher_no"),
				}
			)
		)


class SerialBatchBundle(originalSerialBatchBundle):
	def make_serial_batch_no_bundle(self):
		self.validate_item()
		if self.sle.actual_qty > 0 and self.is_material_transfer():
			self.make_serial_batch_no_bundle_for_material_transfer()
			return

		sn_doc = SerialBatchCreation(
			{
				"item_code": self.item_code,
				"warehouse": self.warehouse,
				"posting_date": self.sle.posting_date,
				"posting_time": self.sle.posting_time,
				"voucher_type": self.sle.voucher_type,
				"voucher_no": self.sle.voucher_no,
				"voucher_detail_no": self.sle.voucher_detail_no,
				"qty": self.sle.actual_qty,
				"avg_rate": self.sle.incoming_rate,
				"total_amount": flt(self.sle.actual_qty) * flt(self.sle.incoming_rate),
				"type_of_transaction": "Inward" if self.sle.actual_qty > 0 else "Outward",
				"company": self.company,
				"is_rejected": self.is_rejected_entry(),
				"make_bundle_from_sle": 1,
				"sle": self.sle,
				"incoming_rate": self.sle.incoming_rate,
				"auto_created_serial_and_batch_bundle": 1
			}
		).make_serial_and_batch_bundle()

		self.set_serial_and_batch_bundle(sn_doc)
	
	def post_process(self):
		if not self.sle.serial_and_batch_bundle and not self.sle.serial_no and not self.sle.batch_no:
			return

		if self.sle.serial_and_batch_bundle:
			docstatus = frappe.get_cached_value(
				"Serial and Batch Bundle", self.sle.serial_and_batch_bundle, "docstatus"
			)

			if docstatus == 0:
				self.submit_serial_and_batch_bundle()
		
		if (
			self.sle.auto_created_serial_and_batch_bundle
			and self.sle.actual_qty > 0
			and self.item_details.has_serial_no
			and not self.item_details.has_batch_no
		):
			return

		if self.item_details.has_serial_no == 1:
			self.set_warehouse_and_status_in_serial_nos()

		if (
			self.sle.actual_qty > 0
			and self.item_details.has_serial_no == 1
			and self.item_details.has_batch_no == 1
		):
			self.set_batch_no_in_serial_nos()

		if self.sle.is_cancelled and self.sle.serial_and_batch_bundle:
			self.cancel_serial_and_batch_bundle()


	def update_serial_no_status_warehouse(self, sle, serial_nos):
		warehouse = sle.warehouse if sle.actual_qty > 0 else None

		if isinstance(serial_nos, str):
			serial_nos = [serial_nos]

		status = "Inactive"
		if sle.actual_qty < 0:
			status = "Delivered"
			if sle.voucher_type == "Stock Entry":
				purpose = frappe.get_cached_value("Stock Entry", sle.voucher_no, "purpose")
				if purpose in [
					"Manufacture",
					"Material Issue",
					"Repack",
					"Material Consumption for Manufacture",
				]:
					status = "Consumed"

		customer = None
		if sle.voucher_type in ["Sales Invoice", "Delivery Note"] and sle.actual_qty < 0:
			customer = frappe.get_cached_value(sle.voucher_type, sle.voucher_no, "customer")

		sn_table = frappe.qb.DocType("Serial No")

		query = (
			frappe.qb.update(sn_table)
			.set(sn_table.warehouse, warehouse)
			.set(sn_table.custom_barcode, Concat(warehouse, " - ", sn_table.serial_no))
			.set(
				sn_table.status,
				"Active"
				if warehouse
				else status
				if (sn_table.purchase_document_no != sle.voucher_no or sle.is_cancelled != 1)
				else "Inactive",
			)
			.set(sn_table.company, sle.company)
			.set(sn_table.customer, customer)
			.where(sn_table.name.isin(serial_nos))
		)

		if status == "Delivered":
			warranty_period = frappe.get_cached_value("Item", sle.item_code, "warranty_period")
			if warranty_period:
				warranty_expiry_date = add_days(sle.posting_date, cint(warranty_period))
				query = query.set(sn_table.warranty_expiry_date, warranty_expiry_date)
				query = query.set(sn_table.warranty_period, warranty_period)
		else:
			query = query.set(sn_table.warranty_expiry_date, None)
			query = query.set(sn_table.warranty_period, 0)

		query.run()

	def validate_item_and_warehouse(self):
		# Sheck if the item row from which the item is taken is connected to a PR
		is_linked_to_pr = frappe.db.exists(
            "Stock Entry Detail",
            {
                "parent": self.sle.voucher_no,
                "item_code": self.sle.item_code,
                "reference_purchase_receipt": ["is", "set"] # This checks if the field is not NULL or empty
            }
        )
		# Skipping validation as when a SE is connected to PR,we are making the Serial no in SE not in PR so it will give error in validation
		if self.sle.voucher_type == "Stock Entry" and is_linked_to_pr:
			pass

		else:
			if self.sle.serial_and_batch_bundle and not frappe.db.exists(
				"Serial and Batch Bundle",
				{
					"name": self.sle.serial_and_batch_bundle,
					"item_code": self.item_code,
					"warehouse": self.warehouse,
					"voucher_no": self.sle.voucher_no,
				},
			):
				msg = f"""
						The Serial and Batch Bundle
						{bold(self.sle.serial_and_batch_bundle)}
						does not belong to Item {bold(self.item_code)}
						or Warehouse {bold(self.warehouse)}
						or {self.sle.voucher_type} no {bold(self.sle.voucher_no)}
					"""

				frappe.throw(_(msg))



def generate_barcode_pdf(serial_nos_details, item_code, warehouse, batch_no=""):
    """Generate barcode PDF with 2 barcodes per page horizontally"""
    try:
        # Create temporary directory for barcode images
        temp_dir = tempfile.mkdtemp()
        
        # Prepare data for PDF generation
        barcode_data = []
        for detail in serial_nos_details:
            serial_no = detail[1]  # serial_no is at index 1
            custom_barcode = detail[14]  # custom_barcode is at index 14
            
            barcode_data.append({
                'serial_no': serial_no,
                'custom_barcode': custom_barcode,
                'item_code': item_code,
                'warehouse': warehouse,
                'batch_no': batch_no
            })
        
        # Generate PDF
        pdf_path = create_barcode_pdf(barcode_data, temp_dir, item_code)
        
        # Save PDF as file in ERPNext
        save_barcode_pdf_to_erpnext(pdf_path, item_code, warehouse, batch_no)
        
        # Clean up temporary files
        cleanup_temp_files(temp_dir)
        
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f"Error generating barcode PDF: {str(e)}", "Barcode PDF Generation")
        raise

def create_barcode_pdf(barcode_data, temp_dir, item_code):
    """Create PDF with barcodes - 2 per page horizontally"""
    # Create PDF file path
    pdf_filename = f"barcode_{item_code}_{frappe.utils.now()}.pdf".replace(" ", "_").replace(":", "-")
    pdf_path = os.path.join(temp_dir, pdf_filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Process barcodes in pairs (2 per page)
    for i in range(0, len(barcode_data), 2):
        # Create table data for current pair
        table_data = []
        row_images = []
        row_info = []
        
        # First barcode
        barcode1 = barcode_data[i]
        img1_path = generate_barcode_image(barcode1['custom_barcode'], temp_dir)
        row_images.append(Image(img1_path, width=3*inch, height=1*inch))
        
        info1 = f"""
        Item Code: {barcode1['item_code']}
        Serial No: {barcode1['serial_no']}
        Warehouse: {barcode1['warehouse']}
        Batch: {barcode1.get('batch_no', 'N/A')}
        Barcode: {barcode1['custom_barcode']}
        """
        row_info.append(Paragraph(info1, styles['Normal']))
        
        # Second barcode (if exists)
        if i + 1 < len(barcode_data):
            barcode2 = barcode_data[i + 1]
            img2_path = generate_barcode_image(barcode2['custom_barcode'], temp_dir)
            row_images.append(Image(img2_path, width=3*inch, height=1*inch))
            
            info2 = f"""
            Item Code: {barcode2['item_code']}
            Serial No: {barcode2['serial_no']}
            Warehouse: {barcode2['warehouse']}
            Batch: {barcode2.get('batch_no', 'N/A')}
            Barcode: {barcode2['custom_barcode']}
            """
            row_info.append(Paragraph(info2, styles['Normal']))
        else:
            # Add empty cell if odd number of barcodes
            row_images.append("")
            row_info.append("")
        
        # Create table with images and info
        table_data = [row_images, row_info]
        
        table = Table(table_data, colWidths=[4*inch, 4*inch])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, 1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 0.5*inch))
    
    # Build PDF
    doc.build(story)
    return pdf_path

def generate_barcode_image(barcode_text, temp_dir):
    """Generate barcode image and return file path"""
    try:
        # Use Code128 barcode format
        code128 = barcode.get_barcode_class('code128')
        barcode_instance = code128(barcode_text, writer=ImageWriter())
        
        # Generate image
        image_filename = f"barcode_{barcode_text}.png".replace(" ", "_").replace("/", "_")
        image_path = os.path.join(temp_dir, image_filename)
        
        # Save barcode image
        barcode_instance.save(image_path.replace('.png', ''))
        
        return image_path + '.png'
        
    except Exception as e:
        frappe.log_error(f"Error generating barcode image for {barcode_text}: {str(e)}")
        raise

def save_barcode_pdf_to_erpnext(pdf_path, item_code, warehouse, batch_no):
    """Save generated PDF as File document in ERPNext"""
    try:
        # Read PDF file
        with open(pdf_path, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
        
        # Create file name
        timestamp = frappe.utils.now().replace(" ", "_").replace(":", "-")
        filename = f"Barcode_{item_code}_{warehouse}_{timestamp}.pdf"
        
        # Create File document
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "content": pdf_content,
            "is_private": 0,
            "folder": "Home/Attachments"
        })
        
        file_doc.insert(ignore_permissions=True)
        
        # Log success
        frappe.msgprint(f"Barcode PDF generated successfully: {file_doc.file_url}")
        
        return file_doc.name
        
    except Exception as e:
        frappe.log_error(f"Error saving PDF to ERPNext: {str(e)}")
        raise

def cleanup_temp_files(temp_dir):
    """Clean up temporary files and directory"""
    try:
        import shutil
        shutil.rmtree(temp_dir)
    except Exception as e:
        frappe.log_error(f"Error cleaning up temp files: {str(e)}")



@frappe.request_cache
def is_internal_supplier(voucher_type, voucher_no):
	return frappe.db.get_value(voucher_type, voucher_no, "is_internal_supplier")