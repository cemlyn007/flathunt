from rightmove.models.base import CamelCaseModel
from rightmove.models.property_image import PropertyImage


class PropertyImages(CamelCaseModel):
    images: list[PropertyImage]
    main_image_src: str
    main_map_image_src: str
