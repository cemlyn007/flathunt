import math
from collections.abc import Iterable

import httpx

from tfl import models
from tfl.api._http import get


async def get_stop_points_by_mode(
    client: httpx.AsyncClient, modes: Iterable[models.ModeId]
) -> list[models.StopPointDetail]:
    modes_str = ",".join(mode.value for mode in modes)
    url = f"/StopPoint/Mode/{modes_str}"

    first = models.StopPointsResponse.model_validate_json(
        (await get(client, url, {"page": 1}))[1]
    )
    stop_points = list(first.stop_points)

    if first.total and first.page_size and first.total > first.page_size:
        total_pages = math.ceil(first.total / first.page_size)
        for page in range(2, total_pages + 1):
            response = models.StopPointsResponse.model_validate_json(
                (await get(client, url, {"page": page}))[1]
            )
            stop_points.extend(response.stop_points)

    return stop_points
