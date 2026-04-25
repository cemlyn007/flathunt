from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.timetable.passenger_flow import PassengerFlow
from tfl.models.json.timetable.train_loading import TrainLoading


class Crowding(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    passenger_flows: list[PassengerFlow] | None = None
    train_loadings: list[TrainLoading] | None = None
