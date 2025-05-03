import ast
import json
import os
from typing import Iterable, Iterator

from tfl import models


class Cache:
    def __init__(self, filepath: str, reset: bool = False):
        self._filepath = filepath
        if reset:
            self._reset()
        self._journeys = self._load()

    def _reset(self) -> None:
        if os.path.exists(self._filepath):
            os.remove(self._filepath)

    def __iter__(
        self,
    ) -> Iterator[tuple[tuple[float, float], tuple[float, float]]]:
        return iter(self._journeys)

    def __getitem__(
        self, from_to: tuple[tuple[float, float], tuple[float, float]]
    ) -> list[models.Journey]:
        return self._journeys[from_to]

    def __setitem__(
        self,
        from_to: tuple[tuple[float, float], tuple[float, float]],
        journeys: list[models.Journey],
    ) -> None:
        self.update([(from_to, journeys)])

    def __contains__(
        self, from_to: tuple[tuple[float, float], tuple[float, float]]
    ) -> bool:
        return from_to in self._journeys

    def update(
        self,
        journeys_iterable: Iterable[
            tuple[tuple[tuple[float, float], tuple[float, float]], list[models.Journey]]
        ],
    ) -> None:
        new_journeys = [
            (from_to, journeys)
            for from_to, journeys in journeys_iterable
            if from_to not in self._journeys or journeys != self._journeys[from_to]
        ]
        if new_journeys:
            rollback_journeys = self._journeys.copy()
            try:
                self._journeys.update(new_journeys)
                self._save()
            except BaseException as exception:
                self._journeys = rollback_journeys
                raise exception

    def _load(
        self,
    ) -> dict[tuple[tuple[float, float], tuple[float, float]], list[models.Journey]]:
        if os.path.exists(self._filepath) and os.path.getsize(self._filepath) > 0:
            with open(self._filepath, "r") as file:
                cache = json.load(file)
            cache = {
                ast.literal_eval(key): [
                    models.Journey.model_validate_json(json.dumps(journey), strict=True)
                    for journey in journeys
                ]
                for key, journeys in cache.items()
            }
            return cache
        # else...
        return {}

    def _save(self) -> None:
        content = json.dumps(
            {
                str(key): [journey.model_dump(mode="json") for journey in journeys]
                for key, journeys in self._journeys.items()
            },
        )
        with open(self._filepath, "w") as file:
            file.write(content)
