from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.api.dependencies import (
    DatabaseDep,
    HttpClientDep,
    RequestLimiterDep,
    SettingsDep,
    bearer_token,
)
from app.core.security import hash_key
from app.services.provider_proxy import (
    parse_json,
    path_is_allowed,
    proxy_request,
    requested_model,
)

router = APIRouter(prefix="/v1", tags=["gateway"])


def token_reservation(
    *, method: str, body: bytes, payload: dict | None, content_type: str, default: int
) -> int:
    """Reserve a conservative budget before starting an upstream request."""
    if method != "POST":
        return 0
    requested_output = 0
    if payload:
        for name in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
            value = payload.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                requested_output = value
                break
    if requested_output == 0:
        requested_output = default
    input_budget = len(body) if "json" in content_type.lower() else default
    return max(input_budget, 1) + requested_output


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def gateway(
    path: str,
    request: Request,
    settings: SettingsDep,
    db: DatabaseDep,
    client: HttpClientDep,
    limiter: RequestLimiterDep,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
):
    clean_path = path.strip("/")
    gateway_key = bearer_token(authorization) if authorization else x_api_key
    if not gateway_key:
        raise HTTPException(status_code=401, detail="Missing gateway key")
    key = db.get_key_by_hash(hash_key(gateway_key))
    if not key or not key["enabled"]:
        raise HTTPException(status_code=401, detail="Gateway key is invalid or disabled")
    if not key["owner_enabled"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    if not key["provider_enabled"]:
        raise HTTPException(status_code=503, detail="Upstream provider is disabled")
    if not key["model_id"] or not key["model_enabled"] or not key["model_name"]:
        raise HTTPException(status_code=403, detail="Gateway key has no active model assignment")
    if not path_is_allowed(clean_path, key["provider_protocol"], settings):
        raise HTTPException(status_code=404, detail="This provider endpoint is not enabled")
    if retry_after := limiter.check(key["owner_id"], key["owner_rpm_limit"]):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry_after)}
        )

    body = await request.body()
    if len(body) > settings.max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Request body is too large"
        )
    try:
        payload = parse_json(body, request.headers.get("content-type", ""))
        model = requested_model(payload, body, request.headers.get("content-type", ""))
        if request.method == "POST" and clean_path != "models":
            if not model:
                raise HTTPException(status_code=400, detail="A model is required")
            if model != key["model_name"]:
                raise HTTPException(
                    status_code=403, detail="This key cannot use the requested model"
                )
        if (
            clean_path.startswith("models/")
            and clean_path.removeprefix("models/") != key["model_name"]
        ):
            raise HTTPException(status_code=403, detail="This key cannot access that model")
        reservation = token_reservation(
            method=request.method,
            body=body,
            payload=payload,
            content_type=request.headers.get("content-type", ""),
            default=settings.default_token_reservation,
        )
        if not db.reserve_tokens(key["owner_id"], reservation):
            raise HTTPException(
                status_code=402,
                detail="Insufficient account token quota for this request",
            )
        return await proxy_request(
            request=request,
            path=clean_path,
            body=body,
            payload=payload,
            key=key,
            client=client,
            settings=settings,
            db=db,
            reserved_tokens=reservation,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Upstream request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Unable to reach upstream provider") from exc
