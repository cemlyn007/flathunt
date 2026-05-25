from pathlib import Path
from typing import Literal

import dagster as dg
from pydantic import Field

from flathunt.defs.config import CommuteDestConfig

_DEFAULT_CACHE_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "cache")


class TflResource(dg.ConfigurableResource):
    api_key: str = dg.EnvVar("FLATHUNT__TFL_API_KEY")


class CacheResource(dg.ConfigurableResource):
    data_dir: str = _DEFAULT_CACHE_DIR


class QueriesResource(dg.ConfigurableResource):
    queries: list[CommuteDestConfig] = Field(default_factory=list)


class SmtpResource(dg.ConfigurableResource):
    host: str = dg.EnvVar("FLATHUNT__SMTP_HOST")
    port: int = 587
    username: str = dg.EnvVar("FLATHUNT__SMTP_USERNAME")
    password: str = dg.EnvVar("FLATHUNT__SMTP_PASSWORD")
    from_address: str = dg.EnvVar("FLATHUNT__SMTP_FROM")
    to_addresses: list[str] = Field(default_factory=list)


class ImapResource(dg.ConfigurableResource):
    host: str = dg.EnvVar("FLATHUNT__IMAP_HOST")
    port: int = 993
    username: str = dg.EnvVar("FLATHUNT__IMAP_USERNAME")
    password: str = dg.EnvVar("FLATHUNT__IMAP_PASSWORD")
    mailbox: str = "[Gmail]/All Mail"


class SearchCriteriaResource(dg.ConfigurableResource):
    channel: Literal["RENT", "BUY"] = "BUY"
    min_budget: float = 400_000
    max_budget: float = 775_000
    has_floorplans: bool = True
    has_images: bool = True
    min_square_meters: float = 75.0
    exclude_below_ground: bool = True
