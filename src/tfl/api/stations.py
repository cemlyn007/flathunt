import httpx

from tfl import models

STATION_FACILITIES_URL = (
    "https://tfl.gov.uk/tfl/syndication/feeds/stations-facilities.xml"
)


async def get_stations_facilities() -> models.Root:
    async with httpx.AsyncClient() as client:
        response = await client.get(STATION_FACILITIES_URL)
        response.raise_for_status()
        content = response.content
    text = content.decode()
    clean_text = " ".join(text.split())
    return models.Root.from_xml(clean_text)
