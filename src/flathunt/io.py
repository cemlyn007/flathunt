from typing import TypeVar

import pydantic

T = TypeVar("T")


def load_json(
    type: type[T],
    filepath: str,
) -> T:
    with open(filepath, "rb") as file:
        content = file.read()
    return pydantic.TypeAdapter(type).validate_json(content)


def save_json(
    type: type[T],
    instance: T,
    filepath: str,
) -> None:
    content = pydantic.TypeAdapter(type).dump_json(instance, indent=2)
    with open(filepath, "wb") as file:
        file.write(content)
