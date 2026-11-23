from datetime import datetime

from pydantic import BaseModel


class RequestView(BaseModel):
    id: int
    key_name: str
    provider_name: str
    endpoint: str
    model: str | None
    status_code: int
    total_tokens: int
    latency_ms: int
    error: str | None
    created_at: datetime


class RequestPage(BaseModel):
    items: list[RequestView]
    total: int
    page: int
    page_size: int


class RequestDetailView(RequestView):
    method: str
    query_string: str | None
    input_tokens: int
    output_tokens: int
    request_headers: str | None
    request_body: str | None
    response_headers: str | None
    response_body: str | None
    detail_truncated: bool
