"""Tests for flathunt.filters - null-safety for size and commute filters."""

import rightmove.models
from flathunt.coords import CommuteDest
from flathunt.filters import check_property_size, filter_by_commute

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _map_property(
    *,
    id: int = 1,
    display_size: str | None = None,
    property_url: str | None = "http://rightmove.co.uk/properties/1",
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
        property_url=property_url,
    )


def _dest(max_duration: float = 60.0) -> CommuteDest:
    return CommuteDest(lon=-0.1, lat=51.5, max_duration=max_duration)


# ---------------------------------------------------------------------------
# check_property_size
# ---------------------------------------------------------------------------


class TestCheckPropertySize:
    def test_check_property_size_keeps_unknown_size(self):
        """A property with no size information must be kept (returns True)."""
        prop = _map_property(display_size=None)
        assert check_property_size(prop, 75.0) is True

    def test_check_property_size_keeps_meeting_threshold(self):
        """A property whose size meets the threshold is kept."""
        prop = _map_property(display_size="80 sqm")
        assert check_property_size(prop, 75.0) is True

    def test_check_property_size_rejects_below_threshold(self):
        """A property whose size is below the threshold is rejected."""
        prop = _map_property(display_size="50 sqm")
        assert check_property_size(prop, 75.0) is False


# ---------------------------------------------------------------------------
# filter_by_commute
# ---------------------------------------------------------------------------


class TestFilterByCommute:
    def test_filter_by_commute_keeps_unknown_duration(self):
        """A property with a None (unknown) commute duration must be KEPT."""
        prop = _map_property(id=1)
        dest = _dest(max_duration=60.0)
        # One destination, duration unknown (None)
        result = filter_by_commute([prop], [[None]], [dest])
        assert len(result) == 1
        assert result[0][0] is prop

    def test_filter_by_commute_rejects_known_over_limit(self):
        """A property with a known duration above the destination max is REJECTED."""
        prop = _map_property(id=1)
        dest = _dest(max_duration=30.0)
        result = filter_by_commute([prop], [[45]], [dest])
        assert result == []

    def test_filter_by_commute_keeps_within_limit(self):
        """A property with all known durations within limits is KEPT."""
        prop = _map_property(id=1)
        dest = _dest(max_duration=60.0)
        result = filter_by_commute([prop], [[30]], [dest])
        assert len(result) == 1
        assert result[0][0] is prop

    def test_filter_by_commute_mixed_unknown_and_known_within_limit(self):
        """Multiple destinations: None for one, known+ok for another → KEPT."""
        prop = _map_property(id=1)
        dest1 = _dest(max_duration=60.0)
        dest2 = _dest(max_duration=45.0)
        result = filter_by_commute([prop], [[None, 30]], [dest1, dest2])
        assert len(result) == 1

    def test_filter_by_commute_mixed_unknown_and_known_over_limit(self):
        """Multiple destinations: None for one, known+exceeded for another → REJECTED."""
        prop = _map_property(id=1)
        dest1 = _dest(max_duration=60.0)
        dest2 = _dest(max_duration=45.0)
        result = filter_by_commute([prop], [[None, 90]], [dest1, dest2])
        assert result == []

    def test_filter_by_commute_returns_durations_alongside_property(self):
        """Return shape is (property, durations) pairs."""
        prop = _map_property(id=1)
        dest = _dest(max_duration=60.0)
        durations = [30]
        result = filter_by_commute([prop], [durations], [dest])
        assert result[0] == (prop, durations)
