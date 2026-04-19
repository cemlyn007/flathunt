from enum import StrEnum

import httpx

from tfl import models
from tfl.api._transport import get


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


async def get_timetable(
    client: httpx.AsyncClient,
    station_id: str,
    from_stop_point_id: str,
    app_key: str,
    direction: Direction | None = None,
) -> models.TimetableResponse:
    url = f"/Line/{station_id}/Timetable/{from_stop_point_id}"
    parameters = {"direction": direction.value} if direction else {}
    parameters["app_key"] = app_key
    _, content = await get(client, url, parameters)
    return models.TimetableResponse.model_validate_json(content, strict=True)


async def get_timetable_between_stops(
    client: httpx.AsyncClient,
    line_id: str,
    from_stop_point_id: str,
    to_stop_point_id: str,
    app_key: str,
) -> models.TimetableResponse:
    url = f"/Line/{line_id}/Timetable/{from_stop_point_id}/to/{to_stop_point_id}"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.TimetableResponse.model_validate_json(content, strict=True)
