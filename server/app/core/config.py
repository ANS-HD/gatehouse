from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com"
    admin_email: str = "admin@example.com"
    admin_password: SecretStr
    session_secret: SecretStr
    registration_enabled: bool = True
    database_path: str = "./gateway.db"
    allowed_origins: str = "http://localhost:5173"
    allowed_path_prefixes: str = (
        "responses,chat/completions,embeddings,models,moderations,images,audio"
    )
    default_rpm: int = 30
    request_timeout_seconds: float = 180
    max_body_bytes: int = 8 * 1024 * 1024
    session_ttl_seconds: int = 8 * 60 * 60
    detailed_logging_enabled: bool = True
    detailed_log_retention_days: int = 7
    detailed_log_max_bytes: int = 64 * 1024
    default_token_reservation: int = 2048
    allow_insecure_upstreams: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("admin_password")
    @classmethod
    def strong_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if len(password) < 8:
            raise ValueError("ADMIN_PASSWORD must contain at least 8 characters")
        if password == "replace-with-a-long-password":
            raise ValueError("ADMIN_PASSWORD must be changed from the example value")
        return value

    @field_validator("admin_email")
    @classmethod
    def normalize_admin_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("session_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        if secret == "replace-with-at-least-32-random-characters":
            raise ValueError("SESSION_SECRET must be changed from the example value")
        return value

    @field_validator("detailed_log_retention_days")
    @classmethod
    def valid_retention(cls, value: int) -> int:
        if value < 1:
            raise ValueError("DETAILED_LOG_RETENTION_DAYS must be at least 1")
        return value

    @field_validator("detailed_log_max_bytes")
    @classmethod
    def valid_log_size(cls, value: int) -> int:
        if value < 1024:
            raise ValueError("DETAILED_LOG_MAX_BYTES must be at least 1024")
        return value

    @field_validator("default_token_reservation")
    @classmethod
    def valid_token_reservation(cls, value: int) -> int:
        if value < 1:
            raise ValueError("DEFAULT_TOKEN_RESERVATION must be at least 1")
        return value

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def path_prefixes(self) -> tuple[str, ...]:
        return tuple(
            item.strip().strip("/")
            for item in self.allowed_path_prefixes.split(",")
            if item.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
