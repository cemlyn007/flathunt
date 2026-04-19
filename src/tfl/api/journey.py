import datetime
import urllib.parse
from collections.abc import Iterable
from typing import Any

import httpx

from tfl import models
from tfl.api._transport import get


async def get_journey_results(
    client: httpx.AsyncClient,
    from_location: tuple[float, float] | str,
    to_location: tuple[float, float] | str,
    arrival_datetime: datetime.datetime | None,
    modes: Iterable[models.ModeId],
    use_multi_modal_call: bool,
    app_key: str,
) -> models.JourneyResults | models.DisambiguationResult:
    url = build_journey_url(from_location, to_location)
    parameters = build_journey_parameters(
        arrival_datetime, modes, use_multi_modal_call, app_key
    )
    status_code, content = await get(client, url, parameters)
    if status_code == 300:
        return models.DisambiguationResult.model_validate_json(content, strict=True)
    return models.JourneyResults.model_validate_json(content, strict=True)


def build_journey_url(
    from_location: tuple[float, float] | str, to_location: tuple[float, float] | str
) -> str:
    from_location_encoded = urllib.parse.quote(
        from_location
        if isinstance(from_location, str)
        else ",".join(map(str, from_location))
    )
    to_location_encoded = urllib.parse.quote(
        to_location if isinstance(to_location, str) else ",".join(map(str, to_location))
    )
    url = f"/Journey/JourneyResults/{from_location_encoded}/to/{to_location_encoded}"
    return url


def build_journey_parameters(
    arrival_datetime: datetime.datetime | None,
    modes: Iterable[models.ModeId],
    use_multi_modal_call: bool,
    app_key: str,
) -> dict[str, Any]:
    parameters = {
        "app_key": app_key,
        "mode": ",".join(mode.value for mode in modes),
        "multiModalCall": use_multi_modal_call,
    }
    if arrival_datetime is None:
        departure_datetime = datetime.datetime.now(tz=datetime.UTC)
        date = departure_datetime.strftime("%Y%m%d")
        time = departure_datetime.strftime("%H%M")
        parameters["date"] = date
        parameters["time"] = time
        parameters["timeIs"] = "departing"
    else:
        arrival_datetime = arrival_datetime.astimezone(datetime.UTC)
        date = arrival_datetime.strftime("%Y%m%d")
        time = arrival_datetime.strftime("%H%M")
        parameters["date"] = date
        parameters["time"] = time
        parameters["timeIs"] = "arriving"
    return parameters
