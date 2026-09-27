from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

ProviderProtocol = Literal["openai", "anthropic"]


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    protocol: ProviderProtocol
    base_url: HttpUrl
    api_key: str = Field(min_length=1, max_length=512)
    models: list[str] = Field(min_length=1, max_length=100)
    enabled: bool = True

    @field_validator("name", "api_key")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return value.strip()

    @field_validator("models")
    @classmethod
    def normalize_models(cls, value: list[str]) -> list[str]:
        models = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not models or any(len(item) > 128 for item in models):
            raise ValueError("At least one valid model is required")
        return models


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    protocol: ProviderProtocol | None = None
    base_url: HttpUrl | None = None
    api_key: str | None = Field(default=None, min_length=1, max_length=512)
    models: list[str] | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None

    @field_validator("models")
    @classmethod
    def normalize_models(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        models = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not models or any(len(item) > 128 for item in models):
            raise ValueError("At least one valid model is required")
        return models


class ProviderModelView(BaseModel):
    id: str
    name: str


class ProviderView(BaseModel):
    id: str
    name: str
    protocol: ProviderProtocol
    base_url: str
    enabled: bool
    created_at: datetime
    key_hint: str
    models: list[ProviderModelView]
