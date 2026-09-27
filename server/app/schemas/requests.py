from datetime import datetime

from pydantic import BaseModel


class RequestDetailView(BaseModel):
    id: int
    key_name: str
    provider_name: str
    method: str
    endpoint: str
    query_string: str | None
    model: str | None
    status_code: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    error: str | None
    created_at: datetime
    request_headers: str | None
    request_body: str | None
    response_headers: str | None
    response_body: str | None
    detail_truncated: bool
