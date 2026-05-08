import pytest

from zoopla.client import ZooplaClient
from zoopla.models import ZooplaListingDetail

_FOR_SALE_URL = "https://www.zoopla.co.uk/for-sale/details/73024330/"
_NEW_HOMES_URL = "https://www.zoopla.co.uk/new-homes/details/72516366/"


@pytest.mark.regression
@pytest.mark.parametrize(
    "url, expected",
    [
        (
            _FOR_SALE_URL,
            {
                "listing_id": "73024330",
                "price_gbp": 995000,
                "address": "Lombard Road, London SW11",
                "property_type": "3 bed flat for sale",
                "bedrooms": 3,
                "bathrooms": 2,
                "tenure": "Leasehold (986 years)",
                "council_tax_band": "F",
                "agent_name": "Savills - Battersea Park",
                "listing_condition": "pre-owned",
            },
        ),
        (
            _NEW_HOMES_URL,
            {
                "listing_id": "72516366",
                "price_gbp": 749900,
                "address": "Finchley Central, Finchley, London N3",
                "property_type": "2 bed bungalow for sale",
                "bedrooms": 2,
                "bathrooms": 1,
                "floor_area_sqft": 792,
                "agent_name": "Foxtons - New Homes North",
                "listing_condition": "new",
            },
        ),
    ],
)
async def test_get_listing_detail_smoke(url: str, expected: dict) -> None:
    async with ZooplaClient() as client:
        detail = await client.get_listing_detail(url)

    assert isinstance(detail, ZooplaListingDetail)
    assert detail.url == url.split("?")[0].rstrip("/") + "/"

    for field, value in expected.items():
        assert getattr(detail, field) == value, f"{field} mismatch"

    assert detail.latitude is not None
    assert detail.longitude is not None
    assert len(detail.image_urls) > 0
    assert detail.description
    assert len(detail.key_features) > 0
