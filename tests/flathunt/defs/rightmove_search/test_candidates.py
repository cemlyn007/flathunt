"""Tests for the candidate_predicate helper in rightmove_search.candidates."""

import rightmove.models
from flathunt.defs.resources import SearchCriteriaResource
from flathunt.defs.rightmove_search.candidates import _candidate_predicate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_criteria(
    *,
    min_square_meters: float = 30.0,
    has_images: bool = True,
    has_floorplans: bool = True,
) -> SearchCriteriaResource:
    return SearchCriteriaResource(
        min_square_meters=min_square_meters,
        has_images=has_images,
        has_floorplans=has_floorplans,
    )


def _map_property(
    *,
    id: int = 1,
    property_url: str | None = "http://rightmove.co.uk/properties/1",
    number_of_images: int | None = 5,
    number_of_floorplans: int | None = 1,
    display_size: str | None = None,
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
        number_of_images=number_of_images,
        number_of_floorplans=number_of_floorplans,
        bedrooms=None,
        bathrooms=None,
        property_url=property_url,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCandidatePredicate:
    def test_candidate_predicate_keeps_unknown_image_count(self):
        """A property with number_of_images=None and has_images=True must be KEPT."""
        sc = _search_criteria(has_images=True)
        prop = _map_property(number_of_images=None, number_of_floorplans=1)
        assert _candidate_predicate(prop, sc) is True

    def test_candidate_predicate_keeps_unknown_floorplan_count(self):
        """A property with number_of_floorplans=None and has_floorplans=True must be KEPT."""
        sc = _search_criteria(has_floorplans=True)
        prop = _map_property(number_of_images=5, number_of_floorplans=None)
        assert _candidate_predicate(prop, sc) is True

    def test_candidate_predicate_rejects_no_url(self):
        """A property without a URL must always be rejected (hard gate)."""
        sc = _search_criteria()
        prop = _map_property(property_url=None)
        assert _candidate_predicate(prop, sc) is False

    def test_candidate_predicate_rejects_few_images_when_required(self):
        """A property with 2 images when has_images=True must be rejected."""
        sc = _search_criteria(has_images=True)
        prop = _map_property(number_of_images=2, number_of_floorplans=1)
        assert _candidate_predicate(prop, sc) is False

    def test_candidate_predicate_keeps_sufficient_images(self):
        """A property with >2 images when has_images=True is kept."""
        sc = _search_criteria(has_images=True)
        prop = _map_property(number_of_images=3, number_of_floorplans=1)
        assert _candidate_predicate(prop, sc) is True

    def test_candidate_predicate_skips_image_check_when_not_required(self):
        """When has_images=False, even 0 images is fine."""
        sc = _search_criteria(has_images=False)
        prop = _map_property(number_of_images=0, number_of_floorplans=1)
        assert _candidate_predicate(prop, sc) is True

    def test_candidate_predicate_rejects_no_floorplan_when_required(self):
        """A property with 0 floorplans when has_floorplans=True must be rejected."""
        sc = _search_criteria(has_floorplans=True)
        prop = _map_property(number_of_images=5, number_of_floorplans=0)
        assert _candidate_predicate(prop, sc) is False

    def test_candidate_predicate_keeps_unknown_size(self):
        """A property with display_size=None must be kept (null-safe size check)."""
        sc = _search_criteria(min_square_meters=75.0)
        prop = _map_property(display_size=None)
        assert _candidate_predicate(prop, sc) is True

    def test_candidate_predicate_rejects_known_size_below_threshold(self):
        """A property with a known size below threshold must be rejected."""
        sc = _search_criteria(min_square_meters=75.0)
        prop = _map_property(display_size="50 sqm")
        assert _candidate_predicate(prop, sc) is False
