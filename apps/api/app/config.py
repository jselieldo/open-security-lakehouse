from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///:memory:"
    osl_api_token: SecretStr = Field(min_length=32)
    collector_api_token: SecretStr | None = Field(default=None, min_length=32)
    s3_endpoint_url: str = "http://localhost:8333"
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket: str = "osl-security-data"
    max_batch_events: int = Field(default=1000, ge=1, le=10000)
    investigation_object_workers: int = Field(default=8, ge=1, le=16)
    detection_rules_dir: str = "/app/detections/rules"
    detection_scheduler_enabled: bool = True
    source_health_check_minutes: int = Field(default=5, ge=1, le=60)
    alert_webhook_url: str | None = None
    alert_webhook_timeout_seconds: int = Field(default=5, ge=1, le=30)
    auth_mode: Literal["static", "hybrid", "oidc"] = "hybrid"
    oidc_issuer_url: str = "http://127.0.0.1:18080/realms/osl"
    oidc_jwks_url: str = "http://keycloak:8080/realms/osl/protocol/openid-connect/certs"
    oidc_audience: str = "osl-api"
    oidc_client_id: str = "osl-console"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
