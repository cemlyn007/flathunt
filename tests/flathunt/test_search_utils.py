import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec, patch

import tfl.api
import tfl.exceptions
from flathunt.search_utils import fetch_journey_results


def _journey_results(*durations: int) -> SimpleNamespace:
    return SimpleNamespace(
        journeys=[SimpleNamespace(duration=duration) for duration in durations]
    )


def test_fetch_journey_results_uses_fastest_of_upcoming_weekdays():
    client = create_autospec(tfl.api.Tfl, instance=True)
    client.get_journey_results = AsyncMock(
        side_effect=[
            _journey_results(80, 85),
            _journey_results(42, 50),
            _journey_results(60),
        ]
    )
    arrival_datetimes = [
        datetime.datetime(2026, 4, 23, 9, 0, tzinfo=datetime.UTC),
        datetime.datetime(2026, 4, 24, 9, 0, tzinfo=datetime.UTC),
        datetime.datetime(2026, 4, 27, 9, 0, tzinfo=datetime.UTC),
    ]

    with patch(
        "flathunt.search_utils.tfl.api.get_next_weekday_datetimes",
        return_value=arrival_datetimes,
    ):
        duration = asyncio.run(fetch_journey_results(client, -0.1, 51.5, -0.2, 51.6))

    assert duration == 42
    assert client.get_journey_results.await_count == 3


def test_fetch_journey_results_ignores_no_service_days_when_sampling_weekdays():
    client = create_autospec(tfl.api.Tfl, instance=True)
    client.get_journey_results = AsyncMock(
        side_effect=[
            tfl.exceptions.JourneyNotFoundError("no service"),
            _journey_results(55),
        ]
    )
    arrival_datetimes = [
        datetime.datetime(2026, 4, 23, 9, 0, tzinfo=datetime.UTC),
        datetime.datetime(2026, 4, 24, 9, 0, tzinfo=datetime.UTC),
    ]

    with patch(
        "flathunt.search_utils.tfl.api.get_next_weekday_datetimes",
        return_value=arrival_datetimes,
    ):
        duration = asyncio.run(fetch_journey_results(client, -0.1, 51.5, -0.2, 51.6))

    assert duration == 55


def test_fetch_journey_results_returns_none_when_all_sampled_weekdays_fail():
    client = create_autospec(tfl.api.Tfl, instance=True)
    client.get_journey_results = AsyncMock(
        side_effect=[
            tfl.exceptions.JourneyNotFoundError("no service"),
            tfl.exceptions.JourneyNotFoundError("still no service"),
        ]
    )
    arrival_datetimes = [
        datetime.datetime(2026, 4, 23, 9, 0, tzinfo=datetime.UTC),
        datetime.datetime(2026, 4, 24, 9, 0, tzinfo=datetime.UTC),
    ]

    with patch(
        "flathunt.search_utils.tfl.api.get_next_weekday_datetimes",
        return_value=arrival_datetimes,
    ):
        duration = asyncio.run(fetch_journey_results(client, -0.1, 51.5, -0.2, 51.6))

    assert duration is None
