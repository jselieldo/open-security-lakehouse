from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///:memory:"
    osl_api_token: SecretStr = Field(min_length=32)
    s3_endpoint_url: str = "http://localhost:8333"
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket: str = "osl-security-data"
    max_batch_events: int = Field(default=1000, ge=1, le=10000)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
