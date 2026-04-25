import pydantic

from tfl.models.base import TflModel
from tfl.models.instruction_step import InstructionStep


class Instruction(TflModel):
    type: str = pydantic.Field(alias="$type")
    summary: str
    detailed: str
    steps: list[InstructionStep]
