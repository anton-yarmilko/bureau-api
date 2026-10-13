from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./bureau.db"
    # Write endpoints require this key in the X-API-Key header. Without it they
    # refuse every write (fail closed) instead of running open.
    api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
