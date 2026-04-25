from __future__ import annotations

import pydantic

from tfl.models.base import TflModel
from tfl.models.passenger_flow import PassengerFlow
from tfl.models.train_loading import TrainLoading


class Crowding(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    passenger_flows: list[PassengerFlow] | None = None
    train_loadings: list[TrainLoading] | None = None
