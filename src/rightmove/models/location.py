from rightmove.models.base import CamelCaseModel


class Location(CamelCaseModel):
    latitude: float
    longitude: float
