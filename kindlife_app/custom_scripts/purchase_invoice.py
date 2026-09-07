import frappe
from kindlife_app.custom_scripts.utils import update_gst_hsn_code


def validate(doc, method):
    update_gst_hsn_code(doc)
