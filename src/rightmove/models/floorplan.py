import pydantic


class Floorplan(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    url: str
    caption: str | None = None
