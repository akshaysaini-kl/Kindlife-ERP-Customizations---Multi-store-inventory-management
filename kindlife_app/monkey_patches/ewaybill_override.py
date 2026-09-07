from india_compliance.gst_india.utils.e_waybill import EWaybillData, get_billing_shipping_address_map


def set_party_address_details(self):
    self.set_address_gstin_map()

    transaction_type = 1
    address = get_billing_shipping_address_map(self.doc)
    has_different_to_address = (
        address.ship_to and address.ship_to != address.bill_to
    )

    has_different_from_address = (
        address.ship_from and address.ship_from != address.bill_from
    )

    self.bill_to = self.get_address_details(address.bill_to)
    self.bill_from = self.get_address_details(address.bill_from)

    # Defaults
    # billing state is changed for SEZ, hence copy()
    self.ship_to = self.bill_to.copy()
    self.ship_from = self.bill_from.copy()

    if has_different_to_address and has_different_from_address:
        transaction_type = 4
        self.ship_to = self.get_address_details(address.ship_to)
        self.ship_from = self.get_address_details(address.ship_from)

    elif has_different_from_address:
        transaction_type = 3
        self.ship_from = self.get_address_details(address.ship_from)

    elif has_different_to_address:
        transaction_type = 2
        self.ship_to = self.get_address_details(address.ship_to)
    print("transaction_type",transaction_type)
    #transaction type is always 4 for kindlife
    self.transaction_details.transaction_type = 4

    to_party = self.transaction_details.party_name
    from_party = self.transaction_details.company_name

    if self.doc.doctype in (
        "Purchase Invoice",
        "Purchase Receipt",
        "Subcontracting Receipt",
    ):
        to_party, from_party = from_party, to_party

    if self.doc.get("is_return"):
        to_party, from_party = from_party, to_party

    self.bill_to.legal_name = to_party or self.bill_to.address_title
    self.bill_from.legal_name = from_party or self.bill_from.address_title

    if self.doc.gst_category == "SEZ":
        self.bill_to.state_number = 96