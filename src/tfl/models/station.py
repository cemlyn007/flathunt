from pydantic_xml import BaseXmlModel, attr, element

from tfl.models.contact_details import ContactDetails
from tfl.models.entrances import Entrances
from tfl.models.facilities import Facilities
from tfl.models.opening_hours import OpeningHours
from tfl.models.placemark import Placemark
from tfl.models.serving_lines import ServingLines
from tfl.models.zones import Zones


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
