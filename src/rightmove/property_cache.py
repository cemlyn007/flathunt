from typing import Any, Iterable
import json
import os


class PropertyCache:
    def __init__(self, filepath: str, reset: bool = False) -> None:
        self._filepath = filepath
        if reset:
            self._reset()
        self._properties = self._load()

    def _reset(self) -> None:
        if os.path.exists(self._filepath):
            os.remove(self._filepath)

    def _load(self) -> list[dict[str, Any]]:
        if os.path.exists(self._filepath):
            with open(self._filepath, "r") as file:
                return json.load(file)
        # else...
        return []

    def contains_property_id(self, property_id: int) -> bool:
        return any(property["id"] == property_id for property in self._properties)

    def add(self, property: dict[str, Any]) -> None:
        self.update([property])

    def update(self, properties: Iterable[dict[str, Any]]) -> None:
        new_properties = [
            property
            for property in properties
            if not self.contains_property_id(property["id"])
        ]
        if new_properties:
            rollback_properties = self._properties.copy()
            try:
                self._properties.extend(new_properties)
                self._save()
            except BaseException as exception:
                self._properties = rollback_properties
                raise exception

    def _save(self) -> None:
        with open(self._filepath, "w") as file:
            file.write(json.dumps(self._properties))
