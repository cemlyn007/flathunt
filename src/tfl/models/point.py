from pydantic import computed_field
from pydantic_xml import BaseXmlModel, element


class Point(BaseXmlModel, tag="Point"):
    coordinates: str = element(tag="coordinates")

    @computed_field
    @property
    def longitude(self) -> float:
        """Extract longitude from KML coordinates (longitude,latitude,altitude)."""
        return float(self.coordinates.split(",")[0])

    @computed_field
    @property
    def latitude(self) -> float:
        """Extract latitude from KML coordinates (longitude,latitude,altitude)."""
        return float(self.coordinates.split(",")[1])

    @computed_field
    @property
    def altitude(self) -> float:
        """Extract altitude from KML coordinates (longitude,latitude,altitude)."""
        coords = self.coordinates.split(",")
        return float(coords[2]) if len(coords) > 2 else 0.0
