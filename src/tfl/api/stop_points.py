from collections.abc import Iterable

import httpx

from tfl import models
from tfl.api._transport import get


async def get_stop_points_by_mode(
    client: httpx.AsyncClient, modes: Iterable[models.ModeId]
) -> list[models.StopPointDetail]:
    modes_str = ",".join(mode.value for mode in modes)
    url = f"/StopPoint/Mode/{modes_str}"
    status_code, content = await get(client, url, {})
    response = models.StopPointsResponse.model_validate_json(content)
    return response.stop_points
