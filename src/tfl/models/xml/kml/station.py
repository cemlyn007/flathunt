from pydantic_xml import BaseXmlModel, attr, element

from tfl.models.xml.accessibility.contact_details import ContactDetails
from tfl.models.xml.accessibility.entrances import Entrances
from tfl.models.xml.accessibility.facilities import Facilities
from tfl.models.xml.accessibility.opening_hours import OpeningHours
from tfl.models.xml.accessibility.serving_lines import ServingLines
from tfl.models.xml.accessibility.zones import Zones
from tfl.models.xml.kml.placemark import Placemark


class Station(BaseXmlModel, tag="station"):
    id: str = attr()
    type: str = attr()
    name: str = element(tag="name")
    contact_details: ContactDetails = element(tag="contactDetails")
    serving_lines: ServingLines | None = element(tag="servingLines", default=None)
    zones: Zones | None = element(tag="zones", default=None)
    facilities: Facilities | None = element(tag="facilities", default=None)
    entrances: Entrances | None = element(tag="entrances", default=None)
    opening_hours: OpeningHours | None = element(tag="openingHours", default=None)
    placemark: Placemark | None = element(tag="Placemark", default=None)
