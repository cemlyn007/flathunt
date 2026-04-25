import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.journey.instruction_step import InstructionStep


class Instruction(TflModel):
    type: str = pydantic.Field(alias="$type")
    summary: str
    detailed: str
    steps: list[InstructionStep]
