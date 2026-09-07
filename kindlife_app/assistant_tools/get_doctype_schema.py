import frappe
from frappe_assistant_core.core.base_tool import BaseTool

class GetDoctypeSchema(BaseTool):
    def __init__(self):
        super().__init__()
        
        self.name = "get_doctype_schema"
        self.description = "Fetches the schema (field definitions) for a given API Schema."
        self.category = "System"
        self.source_app = "kindlife_app"
        
        self.inputSchema = {
            "type": "object",
            "properties": {
                "api_schema_name": {
                    "type": "string",
                    "description": "The name of the API Schema to get the schema for."
                }
            },
            "required": ["api_schema_name"]
        }

    def execute(self, arguments):
        api_schema_name = arguments.get("api_schema_name")

        try:
            api_schema = frappe.get_doc("API Schema", api_schema_name)
            doctype_name = api_schema.reference_doctype

            # Map source_field → target_key
            field_mapping = {
                d.source_field: d.target_key
                for d in api_schema.get("schema_fields")
            }

            meta = frappe.get_meta(doctype_name)
            fields = []

            # --- Default system fields ---
            default_fields = {
                'name': {'label': 'ID', 'fieldtype': 'Data'},
                'owner': {'label': 'Owner', 'fieldtype': 'Data'},
                'creation': {'label': 'Creation', 'fieldtype': 'Datetime'},
                'modified': {'label': 'Modified', 'fieldtype': 'Datetime'},
                'modified_by': {'label': 'Modified By', 'fieldtype': 'Data'},
                'docstatus': {'label': 'Document Status', 'fieldtype': 'Int'}
            }

            for field_name, schema in default_fields.items():
                fieldname = field_mapping.pop(field_name, field_name)
                fields.append({
                    'fieldname': fieldname,
                    'source_fieldname': field_name,
                    'label': schema['label'],
                    'fieldtype': schema['fieldtype'],
                })

            # --- Process mapped fields ---
            for field in meta.fields:

                # Skip layout fields
                if field.fieldtype in ["Section Break", "Column Break", "HTML"]:
                    continue

                # Only expose fields mapped in API Schema
                if field.fieldname not in field_mapping:
                    continue

                mapped_name = field_mapping[field.fieldname]

                field_info = {
                    "fieldname": mapped_name,
                    "source_fieldname": field.fieldname,
                    "label": field.label,
                    "fieldtype": field.fieldtype,
                }

                # 🔥 CHILD TABLE SUPPORT
                if field.fieldtype == "Table":
                    child_doctype = field.options

                    # Check if child doctype has API Schema
                    child_api_schema_name = frappe.db.get_value(
                        "API Schema",
                        {"reference_doctype": child_doctype},
                        "name"
                    )

                    if child_api_schema_name:
                        child_api_schema = frappe.get_doc("API Schema", child_api_schema_name)

                        child_field_mapping = {
                            d.source_field: d.target_key
                            for d in child_api_schema.get("schema_fields")
                        }

                        child_meta = frappe.get_meta(child_doctype)

                        child_fields = []

                        for child_field in child_meta.fields:
                            if child_field.fieldname in child_field_mapping:
                                child_fields.append({
                                    "fieldname": child_field_mapping[child_field.fieldname],
                                    "source_fieldname": child_field.fieldname,
                                    "label": child_field.label,
                                    "fieldtype": child_field.fieldtype,
                                })

                        field_info["child_doctype"] = child_doctype
                        field_info["child_fields"] = child_fields

                fields.append(field_info)

            return {
                "status": "success",
                "doctype": doctype_name,
                "fields": fields,
            }

        except frappe.DoesNotExistError:
            return {
                "status": "not_found",
                "message": f"API Schema '{api_schema_name}' not found.",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
