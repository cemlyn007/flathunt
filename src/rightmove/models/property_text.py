import pydantic


class PropertyText(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    description: str | None = None
