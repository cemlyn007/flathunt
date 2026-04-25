from collections.abc import Iterable, Sequence
from typing import Literal

import rightmove.models
import rightmove.price
from flathunt.coords import CommuteDest
from flathunt.models import parse_display_size_sqm

# ============================================================================
# Simple filter functions - public APIs
# ============================================================================


def check_property_size(
    property: rightmove.models.MapProperty, min_square_meters: float
) -> bool:
    """Check whether a property meets a minimum floor-area requirement.

    Parses the ``display_size`` field, which may be expressed in square feet
    or square metres. Properties with no size information are considered to
    pass the check.

    Args:
        property: The Rightmove property to check.
        min_square_meters: Minimum acceptable floor area in square metres.

    Returns:
        ``True`` if the property's size is unknown or at least ``min_square_meters``,
        ``False`` if it is known and below the threshold.
    """
    sqm = parse_display_size_sqm(property.display_size)
    if sqm is None:
        return True
    return sqm >= min_square_meters


def filter_properties_by_budget_and_features(
    properties: Iterable[rightmove.models.MapProperty],
    min_budget: float,
    max_budget: float,
    has_floorplans: bool,
    has_images: bool,
    square_meters: float,
    channel: Literal["RENT", "BUY"],
) -> list[rightmove.models.MapProperty]:
    """Filter properties by price, size, images, and floorplan availability.

    Args:
        properties: Iterable of candidate properties.
        min_budget: Minimum acceptable price (monthly rent or purchase price).
        max_budget: Maximum acceptable price (monthly rent or purchase price).
        has_floorplans: If ``True``, exclude properties without a floorplan.
        has_images: If ``True``, exclude properties with fewer than 3 images.
        square_meters: Minimum acceptable floor area in square metres.
        channel: Listing channel used to interpret the price field;
            ``"RENT"`` normalises to a monthly figure, ``"BUY"`` uses the raw amount.

    Returns:
        A list of properties that satisfy all specified criteria.
    """
    return [
        p
        for p in properties
        if p.property_url is not None
        and check_property_size(p, square_meters)
        and p.price is not None
        and (
            min_budget <= (rightmove.price.normalize(p.price) or 0) <= max_budget
            if channel == "RENT"
            else min_budget <= (p.price.amount or 0) <= max_budget
        )
        and ((p.number_of_images or 0) > 2 or not has_images)
        and ((p.number_of_floorplans or 0) > 0 or not has_floorplans)
    ]


def filter_by_commute(
    properties: Sequence[rightmove.models.MapProperty],
    durations: Sequence[Sequence[int | None]],
    queries: Sequence[CommuteDest],
) -> list[tuple[rightmove.models.MapProperty, Sequence[int | None]]]:
    """Retain only properties whose commute durations satisfy every query's maximum.

    Args:
        properties: Sequence of properties to filter.
        durations: Per-property commute durations (minutes) for each query,
            aligned with ``properties``. ``None`` indicates an unknown duration.
        queries: Sequence of ``CommuteDest`` values defining each commute
            destination and its time limit.

    Returns:
        A list of ``(property, durations)`` pairs where every duration is
        non-``None`` and within the corresponding query's maximum.
    """
    return [
        (prop, prop_durations)
        for prop, prop_durations in zip(properties, durations, strict=True)
        if all(
            d is not None and d <= query.max_duration
            for d, query in zip(prop_durations, queries, strict=True)
        )
    ]
