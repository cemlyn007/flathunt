from pydantic_xml import BaseXmlModel, element


class ContactDetails(BaseXmlModel, tag="contactDetails"):
    address: str = element(tag="address")
    phone: str = element(tag="phone")
