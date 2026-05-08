import datetime
from collections.abc import Iterable

from tfl import models
from tfl.api._http import get_ratelimited_client
from tfl.api.endpoints.journey import get_journey_results
from tfl.api.endpoints.lines import (
    get_all_lines_routes,
    get_lines_by_mode,
    get_stop_points_by_line,
)
from tfl.api.endpoints.stations import get_stations_facilities
from tfl.api.endpoints.stop_points import get_stop_points_by_mode
from tfl.api.endpoints.timetable import (
    Direction,
    get_timetable,
    get_timetable_between_stops,
)


class Tfl:
    def __init__(
        self,
        app_key: str,
    ) -> None:
        self._app_key = app_key
        self._throttled_client = get_ratelimited_client()

    async def get_stations_facilities(self) -> models.Root:
        return await get_stations_facilities()

    async def get_stop_points_by_mode(
        self, modes: Iterable[models.ModeId]
    ) -> list[models.StopPointDetail]:
        return await get_stop_points_by_mode(self._throttled_client, modes)

    async def get_all_lines_routes(self) -> list[models.Line]:
        return await get_all_lines_routes(self._throttled_client, self._app_key)

    async def get_lines_by_mode(
        self, modes: Iterable[models.ModeId]
    ) -> list[models.Line]:
        return await get_lines_by_mode(self._throttled_client, modes, self._app_key)

    async def get_stop_points_by_line(
        self, line_id: str
    ) -> list[models.StopPointDetail]:
        return await get_stop_points_by_line(
            self._throttled_client, line_id, self._app_key
        )

    async def get_journey_results(
        self,
        from_location: tuple[float, float] | str,
        to_location: tuple[float, float] | str,
        arrival_datetime: datetime.datetime | None,
        modes: Iterable[models.ModeId],
        use_multi_modal_call: bool,
    ) -> models.JourneyResults | models.DisambiguationResult:
        return await get_journey_results(
            self._throttled_client,
            from_location,
            to_location,
            arrival_datetime,
            modes,
            use_multi_modal_call,
            app_key=self._app_key,
        )

    async def get_timetable(
        self,
        station_id: str,
        from_stop_point_id: str,
        direction: Direction | None = None,
    ) -> models.TimetableResponse:
        return await get_timetable(
            self._throttled_client,
            station_id,
            from_stop_point_id,
            self._app_key,
            direction,
        )

    async def get_timetable_between_stops(
        self,
        line_id: str,
        from_stop_point_id: str,
        to_stop_point_id: str,
    ) -> models.TimetableResponse:
        return await get_timetable_between_stops(
            self._throttled_client,
            line_id,
            from_stop_point_id,
            to_stop_point_id,
            self._app_key,
        )
