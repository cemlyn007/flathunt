from pydantic_xml import BaseXmlModel, element

from tfl.models.entrance import Entrance


class Entrances(BaseXmlModel, tag="entrances"):
    entrance: list[Entrance] = element(tag="entrance", default=[])
