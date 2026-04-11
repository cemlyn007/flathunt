import pytest
from shapely.geometry.polygon import LinearRing

from flathunt.isochrone import find_min_simplify_tolerance


def make_ring(n_points: int) -> LinearRing:
    """Create a roughly circular LinearRing with n_points vertices."""
    import math

    coords = [
        (math.cos(2 * math.pi * i / n_points), math.sin(2 * math.pi * i / n_points))
        for i in range(n_points)
    ]
    return LinearRing(coords)


def test_returns_original_when_under_limit():
    ring = make_ring(10)
    result, tolerance = find_min_simplify_tolerance(ring, max_coords=1000)
    assert result is ring
    assert tolerance == 0.0


def test_returns_linear_ring_type():
    ring = make_ring(2000)
    result, tolerance = find_min_simplify_tolerance(ring, max_coords=1000)
    assert isinstance(result, LinearRing), (
        f"Expected LinearRing, got {type(result).__name__}"
    )


def test_result_is_under_coord_limit():
    ring = make_ring(2000)
    result, tolerance = find_min_simplify_tolerance(ring, max_coords=1000)
    assert len(list(result.coords)) < 1000


def test_tolerance_is_positive_when_simplified():
    ring = make_ring(2000)
    _, tolerance = find_min_simplify_tolerance(ring, max_coords=1000)
    assert tolerance > 0.0


def test_raises_when_cannot_simplify_enough():
    # A ring with only 4 coords (triangle + closing) cannot be reduced below 4,
    # so requesting max_coords=2 should raise.
    ring = make_ring(500)
    with pytest.raises(ValueError, match="Could not simplify"):
        find_min_simplify_tolerance(ring, max_coords=2)
