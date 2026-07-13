import asyncio
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import dagster as dg
import httpx

import rightmove.models
from flathunt.defs.rightmove_email.property_details import (
    rightmove_email_property_details,
)
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert


def _make_details(
    listing_id: str, **overrides: Any
) -> rightmove.models.PropertyDetails:
    base: dict[str, Any] = {
        "id": listing_id,
        "livingCosts": {"councilTaxExempt": False, "councilTaxIncluded": False},
    }
    base.update(overrides)
    return rightmove.models.PropertyDetails.model_validate(base)


def _make_prop(listing_id: str) -> RightmoveProperty:
    return RightmoveProperty(
        listing_id=listing_id,
        url=f"/properties/{listing_id}",
        image_url=None,
        price_gbp=500000,
        price_text="£500,000",
        price_qualifier=None,
        is_reduced=False,
        property_type=None,
        address="1 Test St",
        marketed_by=None,
        agent_phone=None,
        photo_count=None,
        floorplan_count=None,
    )


def _make_alerts() -> list[RightmovePropertyAlert]:
    return [
        RightmovePropertyAlert(
            message_id="msg-1",
            subject="New Rightmove properties",
            received_at=datetime(2026, 5, 24, 9, 0, 0),
            properties=[_make_prop("1"), _make_prop("2")],
        )
    ]


def test_rightmove_email_property_details_fetches_each_unique_listing(
    tmp_path,
) -> None:
    alerts = _make_alerts()

    cache = MagicMock()
    cache.data_dir = str(tmp_path)

    details_by_id = {"1": _make_details("1"), "2": _make_details("2")}

    def _fake_get(path: str) -> rightmove.models.PropertyDetails:
        listing_id = path.split("/")[-1]
        return details_by_id[listing_id]

    mock_client = MagicMock()
    mock_client.get_property_details = AsyncMock(side_effect=_fake_get)

    with patch(
        "flathunt.defs.rightmove_email.property_details.rightmove.api.Rightmove",
        return_value=mock_client,
    ):
        result = asyncio.run(
            cast(
                Coroutine[
                    Any, Any, dict[str, rightmove.models.PropertyDetailsFetchResult]
                ],
                rightmove_email_property_details(
                    context=dg.build_asset_context(),
                    cache=cache,
                    rightmove_property_alerts=alerts,
                ),
            )
        )

    assert set(result.keys()) == {"1", "2"}
    assert mock_client.get_property_details.await_count == 2
    mock_client.get_property_details.assert_any_await("/properties/1")
    mock_client.get_property_details.assert_any_await("/properties/2")


def test_rightmove_email_property_details_dedupes_across_alerts(
    tmp_path,
) -> None:
    """Listing '1' appears in two alerts; it should only be fetched once."""
    alerts = [
        RightmovePropertyAlert(
            message_id="msg-1",
            subject="Alert 1",
            received_at=datetime(2026, 5, 24, 9, 0, 0),
            properties=[_make_prop("1")],
        ),
        RightmovePropertyAlert(
            message_id="msg-2",
            subject="Alert 2",
            received_at=datetime(2026, 5, 24, 10, 0, 0),
            properties=[_make_prop("1"), _make_prop("2")],
        ),
    ]

    cache = MagicMock()
    cache.data_dir = str(tmp_path)

    details_by_id = {"1": _make_details("1"), "2": _make_details("2")}

    def _fake_get(path: str) -> rightmove.models.PropertyDetails:
        listing_id = path.split("/")[-1]
        return details_by_id[listing_id]

    mock_client = MagicMock()
    mock_client.get_property_details = AsyncMock(side_effect=_fake_get)

    with patch(
        "flathunt.defs.rightmove_email.property_details.rightmove.api.Rightmove",
        return_value=mock_client,
    ):
        result = asyncio.run(
            cast(
                Coroutine[
                    Any, Any, dict[str, rightmove.models.PropertyDetailsFetchResult]
                ],
                rightmove_email_property_details(
                    context=dg.build_asset_context(),
                    cache=cache,
                    rightmove_property_alerts=alerts,
                ),
            )
        )

    assert set(result.keys()) == {"1", "2"}
    assert mock_client.get_property_details.await_count == 2


def test_rightmove_email_property_details_empty_alerts(tmp_path) -> None:
    cache = MagicMock()
    cache.data_dir = str(tmp_path)

    mock_client = MagicMock()
    mock_client.get_property_details = AsyncMock(return_value=MagicMock())

    with patch(
        "flathunt.defs.rightmove_email.property_details.rightmove.api.Rightmove",
        return_value=mock_client,
    ):
        result = asyncio.run(
            cast(
                Coroutine[
                    Any, Any, dict[str, rightmove.models.PropertyDetailsFetchResult]
                ],
                rightmove_email_property_details(
                    context=dg.build_asset_context(),
                    cache=cache,
                    rightmove_property_alerts=[],
                ),
            )
        )

    assert result == {}
    mock_client.get_property_details.assert_not_awaited()


def test_rightmove_email_property_details_confirmed_delisted(tmp_path) -> None:
    """A 404/410 response marks the listing confirmed-delisted, not just failed."""
    alerts = [
        RightmovePropertyAlert(
            message_id="msg-1",
            subject="New Rightmove properties",
            received_at=datetime(2026, 5, 24, 9, 0, 0),
            properties=[_make_prop("1")],
        )
    ]

    cache = MagicMock()
    cache.data_dir = str(tmp_path)

    request = httpx.Request("GET", "https://www.rightmove.co.uk/properties/1")
    response = httpx.Response(410, request=request)
    error = httpx.HTTPStatusError("410 Gone", request=request, response=response)

    mock_client = MagicMock()
    mock_client.get_property_details = AsyncMock(side_effect=error)

    with patch(
        "flathunt.defs.rightmove_email.property_details.rightmove.api.Rightmove",
        return_value=mock_client,
    ):
        result = asyncio.run(
            cast(
                Coroutine[
                    Any, Any, dict[str, rightmove.models.PropertyDetailsFetchResult]
                ],
                rightmove_email_property_details(
                    context=dg.build_asset_context(),
                    cache=cache,
                    rightmove_property_alerts=alerts,
                ),
            )
        )

    assert result["1"].is_delisted is True
    assert result["1"].details is None


def test_rightmove_email_property_details_transient_failure_not_delisted(
    tmp_path,
) -> None:
    """A non-404/410 failure (timeout, 5xx, parse error) must NOT be treated as
    confirmed-delisted -- that would silently drop listings on e.g. a parser
    regression or rate-limiting, rather than surfacing it."""
    alerts = [
        RightmovePropertyAlert(
            message_id="msg-1",
            subject="New Rightmove properties",
            received_at=datetime(2026, 5, 24, 9, 0, 0),
            properties=[_make_prop("1")],
        )
    ]

    cache = MagicMock()
    cache.data_dir = str(tmp_path)

    mock_client = MagicMock()
    mock_client.get_property_details = AsyncMock(
        side_effect=httpx.ConnectTimeout("timed out")
    )

    with patch(
        "flathunt.defs.rightmove_email.property_details.rightmove.api.Rightmove",
        return_value=mock_client,
    ):
        result = asyncio.run(
            cast(
                Coroutine[
                    Any, Any, dict[str, rightmove.models.PropertyDetailsFetchResult]
                ],
                rightmove_email_property_details(
                    context=dg.build_asset_context(),
                    cache=cache,
                    rightmove_property_alerts=alerts,
                ),
            )
        )

    assert result["1"].is_delisted is False
    assert result["1"].details is None
