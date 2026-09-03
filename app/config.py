from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevFlow Agent API"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://devflow:devflow@localhost:5432/devflow"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

