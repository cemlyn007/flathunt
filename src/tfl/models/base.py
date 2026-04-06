import pydantic
import pydantic.alias_generators


class TflModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="forbid",
        serialize_by_alias=True,
    )
