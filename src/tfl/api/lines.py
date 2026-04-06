from collections.abc import Iterable

import httpx

from tfl import models
from tfl.api._transport import get


async def get_all_lines_routes(
    client: httpx.AsyncClient, app_key: str
) -> list[models.Line]:
    url = "/Line/Route"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.LinesRoutesResponse.validate_json(content)


async def get_lines_by_mode(
    client: httpx.AsyncClient, modes: Iterable[models.ModeId], app_key: str
) -> list[models.Line]:
    modes_str = ",".join(mode.value for mode in modes)
    url = f"/Line/Mode/{modes_str}"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.LineList.validate_json(content)


async def get_stop_points_by_line(
    client: httpx.AsyncClient, line_id: str, app_key: str
) -> list[models.StopPointDetail]:
    url = f"/Line/{line_id}/StopPoints"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.StopPointList.validate_json(content)
