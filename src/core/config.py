from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    api_id: int = Field(..., alias="API_ID")
    api_hash: str = Field(..., alias="API_HASH")

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")

    alert_account: str | None = Field(None, alias="ALERT_ACCOUNT")

    google_service_account_file: str | None = Field(
        None, alias="GOOGLE_SERVICE_ACCOUNT_FILE"
    )
    google_service_account: str | None = Field(None, alias="GOOGLE_SERVICE_ACCOUNT")

    logfire_token: str | None = Field(None, alias="LOGFIRE_TOKEN")

    telegram_bot_token: str | None = Field(None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(None, alias="TELEGRAM_CHAT_ID")

    gatus_url: str | None = Field(None, alias="GATUS_URL")
    gatus_token: str | None = Field(None, alias="GATUS_TOKEN")

    testing: bool = Field(default=False, alias="TESTING")


@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()
