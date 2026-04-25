from pydantic_xml import BaseXmlModel, element


class PlatformToTrain(BaseXmlModel, tag="platformToTrain"):
    train_name: str | None = element(tag="trainName", default=None)
    platform_to_train_steps: str | None = element(
        tag="platformToTrainSteps", default=None
    )
