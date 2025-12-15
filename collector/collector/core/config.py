from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "dev"
    app_secret_key: str = "dev-secret-change-me"
    database_url: str = "postgresql+asyncpg://consumables:consumables@db:5432/consumables"
    allow_insecure_mqtt_tls: bool = True


settings = Settings()


