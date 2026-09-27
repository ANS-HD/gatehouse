import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.core.config import Settings
from app.core.security import decrypt_secret, encrypt_secret
from app.storage.database import Database

FORWARDED_RESPONSE_HEADERS = {
    "content-type",
    "request-id",
    "x-request-id",
    "openai-processing-ms",
}
ANTHROPIC_PATHS = ("messages", "models")
SENSITIVE_NAMES = {
    "api_key",
    "authorization",
    "client_secret",
    "cookie",
    "password",
    "refresh_token",
    "set-cookie",
    "token",
    "x-api-key",
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def update(self, data: dict[str, Any]) -> None:
        usage = (
            data.get("usage")
            or (data.get("response") or {}).get("usage")
            or (data.get("message") or {}).get("usage")
        )
        if not isinstance(usage, dict):
            return
        self.input_tokens = max(
            self.input_tokens,
            int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        )
        self.output_tokens = max(
            self.output_tokens,
            int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
        )
        self.total_tokens = max(
            self.total_tokens,
            int(usage.get("total_tokens", self.input_tokens + self.output_tokens) or 0),
        )


class SSEUsageParser:
    def __init__(self) -> None:
        self.buffer = ""
        self.usage = Usage()

    def feed(self, chunk: bytes) -> None:
        self.buffer += chunk.decode("utf-8", errors="ignore")
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()
        for line in lines:
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                self.usage.update(json.loads(raw))
            except json.JSONDecodeError:
                pass


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_NAMES else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def truncate_text(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode()
    if len(encoded) <= max_bytes:
        return value, False
    shortened = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return f"{shortened}\n…[TRUNCATED]", True


def headers_for_log(headers: httpx.Headers | Any, max_bytes: int) -> tuple[str, bool]:
    cleaned = {
        key: "[REDACTED]" if key.lower() in SENSITIVE_NAMES else value
        for key, value in headers.items()
    }
    return truncate_text(json.dumps(cleaned, ensure_ascii=False, indent=2), max_bytes)


def body_for_log(body: bytes, content_type: str, max_bytes: int) -> tuple[str | None, bool]:
    if not body:
        return None, False
    if "json" in content_type:
        try:
            value = json.loads(body)
            text = json.dumps(redact(value), ensure_ascii=False, indent=2)
            return truncate_text(text, max_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    if content_type.startswith("text/") or "event-stream" in content_type:
        return truncate_text(body.decode("utf-8", errors="replace"), max_bytes)
    return f"[BINARY BODY OMITTED: {len(body)} bytes, {content_type or 'unknown'}]", False


def query_for_log(query: str) -> str | None:
    if not query:
        return None
    values = [
        (key, "[REDACTED]" if key.lower() in SENSITIVE_NAMES else value)
        for key, value in parse_qsl(query, keep_blank_values=True)
    ]
    return urlencode(values)


def encrypted(value: str | None, settings: Settings) -> str | None:
    if value is None:
        return None
    return encrypt_secret(value, settings.session_secret.get_secret_value())


def request_log_fields(
    request: Request, body: bytes, settings: Settings
) -> tuple[dict[str, Any], bool]:
    if not settings.detailed_logging_enabled:
        return {"method": request.method}, False
    headers, headers_truncated = headers_for_log(request.headers, settings.detailed_log_max_bytes)
    body_text, body_truncated = body_for_log(
        body,
        request.headers.get("content-type", ""),
        settings.detailed_log_max_bytes,
    )
    return (
        {
            "method": request.method,
            "query_string_encrypted": encrypted(query_for_log(request.url.query), settings),
            "request_headers_encrypted": encrypted(headers, settings),
            "request_body_encrypted": encrypted(body_text, settings),
        },
        headers_truncated or body_truncated,
    )


def response_log_fields(
    headers: httpx.Headers,
    body: bytes,
    settings: Settings,
) -> tuple[dict[str, Any], bool]:
    if not settings.detailed_logging_enabled:
        return {}, False
    header_text, headers_truncated = headers_for_log(headers, settings.detailed_log_max_bytes)
    body_text, body_truncated = body_for_log(
        body,
        headers.get("content-type", ""),
        settings.detailed_log_max_bytes,
    )
    return (
        {
            "response_headers_encrypted": encrypted(header_text, settings),
            "response_body_encrypted": encrypted(body_text, settings),
        },
        headers_truncated or body_truncated,
    )


def path_is_allowed(path: str, protocol: str, settings: Settings) -> bool:
    prefixes = ANTHROPIC_PATHS if protocol == "anthropic" else settings.path_prefixes
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def requested_model(payload: dict[str, Any] | None, body: bytes, content_type: str) -> str | None:
    if payload:
        value = payload.get("model")
        return value.strip() if isinstance(value, str) and value.strip() else None
    if "multipart/form-data" not in content_type.lower() or not body:
        return None
    try:
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") != "model":
                continue
            value = part.get_content()
            return value.strip() if isinstance(value, str) and value.strip() else None
    except (TypeError, ValueError):
        return None
    return None


def response_headers(upstream: httpx.Response) -> dict[str, str]:
    return {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in FORWARDED_RESPONSE_HEADERS
    }


def billable_tokens(usage: Usage, status_code: int, reserved_tokens: int, error: str | None) -> int:
    if usage.total_tokens > 0:
        return usage.total_tokens
    return reserved_tokens if status_code < 400 and error is None else 0


def upstream_headers(request: Request, protocol: str, api_key: str) -> dict[str, str]:
    headers = {
        "Content-Type": request.headers.get("content-type", "application/json"),
        "Accept": request.headers.get("accept", "*/*"),
    }
    if protocol == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = request.headers.get("anthropic-version", "2023-06-01")
        if value := request.headers.get("anthropic-beta"):
            headers["anthropic-beta"] = value
    else:
        headers["Authorization"] = f"Bearer {api_key}"
        for name in ("openai-beta", "x-client-request-id"):
            if value := request.headers.get(name):
                headers[name] = value
    return headers


async def proxy_request(
    *,
    request: Request,
    path: str,
    body: bytes,
    payload: dict[str, Any] | None,
    key: dict[str, Any],
    client: httpx.AsyncClient,
    settings: Settings,
    db: Database,
    reserved_tokens: int = 0,
) -> Response:
    started = time.perf_counter()
    model = requested_model(payload, body, request.headers.get("content-type", ""))
    is_stream = bool(payload and payload.get("stream"))
    request_details: dict[str, Any] = {"method": request.method}
    request_truncated = False
    try:
        request_details, request_truncated = request_log_fields(request, body, settings)
        protocol = key["provider_protocol"]
        api_key = decrypt_secret(
            key["provider_api_key_encrypted"], settings.session_secret.get_secret_value()
        )
        url = f"{key['provider_base_url'].rstrip('/')}/{path}"
        upstream_request = client.build_request(
            request.method,
            url,
            params=request.query_params,
            headers=upstream_headers(request, protocol, api_key),
            content=body or None,
        )
        upstream = await client.send(upstream_request, stream=is_stream)
    except httpx.HTTPError as exc:
        status_code = 504 if isinstance(exc, httpx.TimeoutException) else 502
        try:
            db.record_request(
                key_id=key["id"],
                endpoint=f"/v1/{path}",
                model=model,
                status_code=status_code,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc)[:500] or exc.__class__.__name__,
                **request_details,
                detail_truncated=request_truncated,
            )
        finally:
            db.release_token_reservation(key["owner_id"], reserved_tokens)
        raise
    except BaseException:
        db.release_token_reservation(key["owner_id"], reserved_tokens)
        raise

    if not is_stream:
        try:
            content = await upstream.aread()
            usage = Usage()
            error = None
            try:
                data = json.loads(content)
                usage.update(data)
                if upstream.status_code >= 400:
                    error_data = data.get("error") or {}
                    error = str(error_data.get("message") or "Upstream request failed")[:500]
            except (json.JSONDecodeError, AttributeError):
                error = "Upstream request failed" if upstream.status_code >= 400 else None
            headers = response_headers(upstream)
            response_details, response_truncated = response_log_fields(
                upstream.headers, content, settings
            )
            db.record_request(
                key_id=key["id"],
                endpoint=f"/v1/{path}",
                model=model,
                status_code=upstream.status_code,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=billable_tokens(usage, upstream.status_code, reserved_tokens, error),
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
                **request_details,
                **response_details,
                detail_truncated=request_truncated or response_truncated,
            )
            return Response(content=content, status_code=upstream.status_code, headers=headers)
        except httpx.HTTPError as exc:
            db.record_request(
                key_id=key["id"],
                endpoint=f"/v1/{path}",
                model=model,
                status_code=502,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc)[:500] or exc.__class__.__name__,
                **request_details,
                detail_truncated=request_truncated,
            )
            raise
        finally:
            await upstream.aclose()
            db.release_token_reservation(key["owner_id"], reserved_tokens)

    parser = SSEUsageParser()
    response_buffer = bytearray()
    response_was_truncated = False

    async def stream() -> AsyncIterator[bytes]:
        nonlocal response_was_truncated
        error: str | None = None
        try:
            async for chunk in upstream.aiter_bytes():
                parser.feed(chunk)
                if settings.detailed_logging_enabled:
                    remaining = settings.detailed_log_max_bytes - len(response_buffer)
                    if remaining > 0:
                        response_buffer.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        response_was_truncated = True
                yield chunk
        except httpx.HTTPError as exc:
            error = str(exc)[:500]
            raise
        finally:
            response_details, response_truncated = response_log_fields(
                upstream.headers, bytes(response_buffer), settings
            )
            await upstream.aclose()
            try:
                db.record_request(
                    key_id=key["id"],
                    endpoint=f"/v1/{path}",
                    model=model,
                    status_code=upstream.status_code,
                    input_tokens=parser.usage.input_tokens,
                    output_tokens=parser.usage.output_tokens,
                    total_tokens=billable_tokens(
                        parser.usage, upstream.status_code, reserved_tokens, error
                    ),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=error,
                    **request_details,
                    **response_details,
                    detail_truncated=(
                        request_truncated or response_truncated or response_was_truncated
                    ),
                )
            finally:
                db.release_token_reservation(key["owner_id"], reserved_tokens)

    return StreamingResponse(
        stream(), status_code=upstream.status_code, headers=response_headers(upstream)
    )


def parse_json(body: bytes, content_type: str) -> dict[str, Any] | None:
    if not body or "application/json" not in content_type:
        return None
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    return value if isinstance(value, dict) else None
