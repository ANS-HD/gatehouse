from datetime import datetime

from pydantic import BaseModel, Field


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class KeyUpdate(BaseModel):
    enabled: bool | None = None


class KeyView(BaseModel):
    id: str
    name: str
    provider_id: str
    provider_name: str
    model_id: str | None
    model_name: str | None
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    rpm: int
    token_limit: int | None
    tokens_used: int
    account_tokens_used: int
    enabled: bool


class KeyCreated(KeyView):
    key: str
