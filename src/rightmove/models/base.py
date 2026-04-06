import pydantic
import pydantic.alias_generators


class CamelCaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
        extra="forbid",
    )
