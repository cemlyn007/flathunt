import dagster as dg
from pydantic import Field

from flathunt.defs.config import CommuteDestConfig


class TflResource(dg.ConfigurableResource):
    api_key: str = dg.EnvVar("FLATHUNT__TFL_API_KEY")


class CacheResource(dg.ConfigurableResource):
    data_dir: str = "cache"


class QueriesResource(dg.ConfigurableResource):
    queries: list[CommuteDestConfig] = Field(default_factory=list)


class SmtpResource(dg.ConfigurableResource):
    host: str = dg.EnvVar("FLATHUNT__SMTP_HOST")
    port: int = 587
    username: str = dg.EnvVar("FLATHUNT__SMTP_USERNAME")
    password: str = dg.EnvVar("FLATHUNT__SMTP_PASSWORD")
    from_address: str = dg.EnvVar("FLATHUNT__SMTP_FROM")
    to_addresses: list[str] = Field(default_factory=list)
