from datetime import datetime
from typing import Any, cast

import dagster as dg
import pytest

import rightmove.models
from flathunt.defs.rightmove_email.enriched import (
    _to_final_property,
    rightmove_enriched_properties,
)
from flathunt.models import FinalProperty
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert


def _details(**overrides: Any) -> rightmove.models.PropertyDetails:
    base: dict[str, Any] = {
        "id": "1",
        "livingCosts": {"councilTaxExempt": False, "councilTaxIncluded": False},
    }
    base.update(overrides)
    return rightmove.models.PropertyDetails.model_validate(base)


def test_to_final_property_sets_beds_baths_and_api_size() -> None:
    details = _details(
        bedrooms=2,
        bathrooms=2,
        sizings=[{"unit": "sqm", "minimumSize": 82, "maximumSize": 82}],
    )
    fp = _to_final_property("123", "1 Test St", 500000, details)
    assert fp.bedrooms == 2
    assert fp.bathrooms == 2
    assert fp.display_size == "82 sqm"
    assert fp.extracted_sqm is None


def test_to_final_property_uses_extracted_sqm_when_no_api_size() -> None:
    details = _details(bedrooms=3, bathrooms=1, sizings=[])
    fp = _to_final_property("124", "2 Test St", None, details, extracted_sqm=70.0)
    assert fp.bedrooms == 3
    assert fp.bathrooms == 1
    assert fp.display_size is None
    assert fp.extracted_sqm == pytest.approx(70.0)


def test_to_final_property_blank_when_details_missing() -> None:
    fp = _to_final_property("125", None, None, None)
    assert fp.bedrooms is None
    assert fp.bathrooms is None
    assert fp.display_size is None
    assert fp.extracted_sqm is None


def _make_prop(
    listing_id: str, price_gbp: int | None = 500000, address: str | None = "1 Test St"
) -> RightmoveProperty:
    return RightmoveProperty(
        listing_id=listing_id,
        url=f"/properties/{listing_id}",
        image_url=None,
        price_gbp=price_gbp,
        price_text=f"£{price_gbp:,}" if price_gbp else "POA",
        price_qualifier=None,
        is_reduced=False,
        property_type=None,
        address=address,
        marketed_by=None,
        agent_phone=None,
        photo_count=None,
        floorplan_count=None,
    )


def _make_alerts(props: list[RightmoveProperty]) -> list[RightmovePropertyAlert]:
    return [
        RightmovePropertyAlert(
            message_id="msg-1",
            subject="New Rightmove properties",
            received_at=datetime(2026, 5, 24, 9, 0, 0),
            properties=props,
        )
    ]


def test_rightmove_enriched_properties_assembles_from_details() -> None:
    """Asset consumes pre-fetched details dict and returns FinalProperty list."""
    prop1 = _make_prop("1", price_gbp=400000, address="10 Foo Lane")
    prop2 = _make_prop("2", price_gbp=None, address="20 Bar St")
    alerts = _make_alerts([prop1, prop2])

    details_1 = _details(
        id="1",
        bedrooms=2,
        bathrooms=1,
        sizings=[{"unit": "sqm", "minimumSize": 75, "maximumSize": 75}],
        location={"latitude": 51.5, "longitude": -0.1},
    )
    details_by_id: dict[str, rightmove.models.PropertyDetails | None] = {
        "1": details_1,
        "2": None,
    }

    result = cast(
        list[FinalProperty],
        rightmove_enriched_properties(
            context=dg.build_asset_context(),
            rightmove_property_alerts=alerts,
            rightmove_email_property_details=details_by_id,
        ),
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(fp, FinalProperty) for fp in result)

    fp_by_id = {fp.id: fp for fp in result}

    # listing "1": enriched from details
    fp1 = fp_by_id[1]
    assert fp1.bedrooms == 2
    assert fp1.bathrooms == 1
    assert fp1.display_size == "75 sqm"
    assert fp1.extracted_sqm is None  # no extraction in this asset
    assert fp1.latitude == pytest.approx(51.5)
    assert fp1.longitude == pytest.approx(-0.1)
    assert fp1.price is not None
    assert fp1.price.amount == 400000
    assert fp1.display_address == "10 Foo Lane"

    # listing "2": no details -> fields default to None but address/price from email
    fp2 = fp_by_id[2]
    assert fp2.bedrooms is None
    assert fp2.bathrooms is None
    assert fp2.display_size is None
    assert fp2.extracted_sqm is None
    assert fp2.latitude is None
    assert fp2.price is None
    assert fp2.display_address == "20 Bar St"


def test_rightmove_enriched_properties_empty_alerts() -> None:
    result = cast(
        list[FinalProperty],
        rightmove_enriched_properties(
            context=dg.build_asset_context(),
            rightmove_property_alerts=[],
            rightmove_email_property_details={},
        ),
    )
    assert result == []


def test_rightmove_enriched_properties_dedupes_across_alerts() -> None:
    """Same listing_id in two alerts should only appear once in output."""
    prop = _make_prop("1")
    alerts = [
        RightmovePropertyAlert(
            message_id="msg-1",
            subject="Alert 1",
            received_at=datetime(2026, 5, 24, 9, 0, 0),
            properties=[prop],
        ),
        RightmovePropertyAlert(
            message_id="msg-2",
            subject="Alert 2",
            received_at=datetime(2026, 5, 24, 10, 0, 0),
            properties=[prop],
        ),
    ]
    details_by_id: dict[str, rightmove.models.PropertyDetails | None] = {"1": None}

    result = cast(
        list[FinalProperty],
        rightmove_enriched_properties(
            context=dg.build_asset_context(),
            rightmove_property_alerts=alerts,
            rightmove_email_property_details=details_by_id,
        ),
    )
    assert len(result) == 1
    assert result[0].id == 1
