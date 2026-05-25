"""Tests for the matched_properties asset (pure merge + size filter)."""

from typing import Any

import dagster as dg
import pytest

import rightmove.models
from flathunt.anthropic_extraction import (
    ExtractedAttributes,
    ExtractedPropertyInfo,
    FloorPlanResult,
)
from flathunt.defs.resources import SearchCriteriaResource
from flathunt.defs.rightmove_search.matched_properties import matched_properties
from flathunt.models import MatchedProperty
from tests.flathunt.defs.gate_helpers import drain_gate

# ---------------------------------------------------------------------------
# Shared model-construction helpers (mirror test_extracted_attributes.py)
# ---------------------------------------------------------------------------


def _map_property(
    *, id: int, display_size: str | None = None
) -> rightmove.models.MapProperty:
    return rightmove.models.MapProperty.model_construct(
        id=id,
        display_size=display_size,
        display_address="1 Test Street",
        location=rightmove.models.Location.model_construct(
            latitude=51.5, longitude=-0.1
        ),
        price=rightmove.models.Price.model_construct(
            amount=400_000, frequency="monthly"
        ),
        number_of_images=1,
        number_of_floorplans=1,
        bedrooms=None,
        bathrooms=None,
        property_url=None,
    )


def _details(
    *,
    id: str = "1",
    description: str | None = "A lovely leasehold flat",
    floorplans: list[dict] | None = None,
    size_sqm: float | None = None,
    tenure_type: str | None = None,
    years_remaining_on_lease: int | None = None,
    bedrooms: int | None = None,
    bathrooms: int | None = None,
    annual_service_charge: float | None = None,
    annual_ground_rent: float | None = None,
    council_tax_band: str | None = None,
) -> rightmove.models.PropertyDetails:
    living_costs: dict[str, Any] = {
        "councilTaxExempt": False,
        "councilTaxIncluded": False,
    }
    if annual_service_charge is not None:
        living_costs["annualServiceCharge"] = annual_service_charge
    if annual_ground_rent is not None:
        living_costs["annualGroundRent"] = annual_ground_rent
    if council_tax_band is not None:
        living_costs["councilTaxBand"] = council_tax_band

    raw: dict[str, Any] = {
        "id": id,
        "livingCosts": living_costs,
    }
    if description is not None:
        raw["text"] = {"description": description}
    if floorplans is not None:
        raw["floorplans"] = floorplans
    if size_sqm is not None:
        raw["sizings"] = [
            {"unit": "sqm", "minimumSize": size_sqm, "maximumSize": size_sqm}
        ]
    if tenure_type is not None or years_remaining_on_lease is not None:
        raw["tenure"] = {
            "tenureType": tenure_type,
            "yearsRemainingOnLease": years_remaining_on_lease,
        }
    if bedrooms is not None:
        raw["bedrooms"] = bedrooms
    if bathrooms is not None:
        raw["bathrooms"] = bathrooms

    return rightmove.models.PropertyDetails.model_validate(raw)


def _search_criteria(
    min_square_meters: float = 30.0, exclude_below_ground: bool = True
) -> SearchCriteriaResource:
    return SearchCriteriaResource(
        min_square_meters=min_square_meters,
        exclude_below_ground=exclude_below_ground,
    )


def _run(
    matched: list[MatchedProperty],
    candidates: list[rightmove.models.MapProperty],
    details: dict[int, rightmove.models.PropertyDetails | None],
    extracted: dict[str, ExtractedAttributes],
    min_sqm: float = 30.0,
    exclude_below_ground: bool = True,
):
    sc = _search_criteria(min_sqm, exclude_below_ground)
    value, _ = drain_gate(
        matched_properties(
            context=dg.build_asset_context(),
            search_criteria=sc,
            matched_property_ids=matched,
            candidate_properties=candidates,
            rightmove_property_details=details,
            extracted_attributes=extracted,
        )
    )
    return value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMatchedProperties:
    def test_extracted_attributes_merged_into_final_property(self):
        """extracted_sqm and extracted_council_tax_band come from ExtractedAttributes."""
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None, council_tax_band=None)
        attrs = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(total_sqm=70.0),
                description=ExtractedPropertyInfo(council_tax_band="C"),
            )
        }

        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=30.0)

        assert len(result) == 1
        fp = result[0]
        assert fp.extracted_sqm == pytest.approx(70.0)
        assert fp.extracted_council_tax_band == "C"

    def test_property_dropped_when_extracted_sqm_below_min(self):
        """A property whose only size signal is extracted_sqm below threshold is dropped."""
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(total_sqm=30.0),
            )
        }

        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=50.0)

        assert result == []

    def test_property_kept_when_size_genuinely_unknown(self):
        """A property with empty ExtractedAttributes (no size info at all) is kept."""
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs: dict[str, ExtractedAttributes] = {}  # no entry → ExtractedAttributes()

        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=50.0)

        assert len(result) == 1
        assert result[0].extracted_sqm is None


class TestBelowGroundFilter:
    def test_below_ground_excluded_by_default(self):
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=True),
            )
        }
        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=30.0)
        assert result == []

    def test_below_ground_kept_when_filter_disabled(self):
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=True),
            )
        }
        result = _run(
            matched,
            [candidate],
            {1: detail},
            attrs,
            min_sqm=30.0,
            exclude_below_ground=False,
        )
        assert len(result) == 1
        assert result[0].is_below_ground is True

    def test_unknown_below_ground_kept(self):
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs = {"1": ExtractedAttributes()}  # both signals None -> None
        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=30.0)
        assert len(result) == 1
        assert result[0].is_below_ground is None

    def test_conflicting_signals_kept(self):
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=False),
            )
        }
        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=30.0)
        assert len(result) == 1
        assert result[0].is_below_ground is None

    def test_above_ground_kept(self):
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        candidate = _map_property(id=1, display_size=None)
        detail = _details(id="1", size_sqm=None)
        attrs = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=False),
                description=ExtractedPropertyInfo(below_ground=False),
            )
        }
        result = _run(matched, [candidate], {1: detail}, attrs, min_sqm=30.0)
        assert len(result) == 1
        assert result[0].is_below_ground is False
