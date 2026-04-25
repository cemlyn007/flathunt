import pydantic
import pydantic.alias_generators


class Tenure(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None

    @pydantic.field_validator("years_remaining_on_lease", mode="before")
    @classmethod
    def _reject_zero(cls, v: object) -> object:
        return None if v == 0 else v
