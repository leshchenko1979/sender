from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")
    alert_account: Optional[str] = Field(None, alias="ALERT_ACCOUNT")
    google_service_account_file: Optional[str] = Field(
        None, alias="GOOGLE_SERVICE_ACCOUNT_FILE"
    )
    google_service_account: Optional[str] = Field(None, alias="GOOGLE_SERVICE_ACCOUNT")


@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()
