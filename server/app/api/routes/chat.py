import json
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.api.dependencies import (
    CurrentUser,
    DatabaseDep,
    HttpClientDep,
    RequestLimiterDep,
    SettingsDep,
)
from app.api.routes.gateway import token_reservation
from app.schemas.chat import ChatInput
from app.services.provider_proxy import path_is_allowed, proxy_request

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(
    data: ChatInput,
    request: Request,
    user: CurrentUser,
    db: DatabaseDep,
    settings: SettingsDep,
    client: HttpClientDep,
    limiter: RequestLimiterDep,
) -> Response:
    if len(await request.body()) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body is too large")
    key = db.get_owned_proxy_key(data.key_id, user["id"])
    if not key:
        raise HTTPException(status_code=404, detail="访问密钥不存在")
    if not key["enabled"] or not key["owner_enabled"]:
        raise HTTPException(status_code=403, detail="账户或访问密钥已停用")
    if not db.user_can_use_model(
        user["id"], key["provider_id"], key["model_id"], user["is_admin"]
    ):
        raise HTTPException(status_code=403, detail="该模型尚未授权或已停用，请联系管理员")

    anthropic = key["provider_protocol"] == "anthropic"
    path = "messages" if anthropic else "chat/completions"
    if not path_is_allowed(path, key["provider_protocol"], settings):
        raise HTTPException(status_code=404, detail="当前供应商未开放聊天接口")
    if retry_after := limiter.check(user["id"], user["rpm_limit"]):
        raise HTTPException(
            status_code=429, detail="请求过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
    model = key["model_name"]
    model_name = model.rsplit("/", 1)[-1]
    completion_limit = not anthropic and re.match(r"^(?:gpt-[5-9]|o\d)(?:[.-]|$)", model_name)
    payload = {
        "model": model,
        "messages": [message.model_dump() for message in data.messages],
        "stream": data.stream,
        "max_completion_tokens" if completion_limit else "max_tokens": data.max_output_tokens,
    }
    if data.stream and not anthropic:
        payload["stream_options"] = {"include_usage": True}
    body = json.dumps(payload, ensure_ascii=False).encode()
    if len(body) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Conversation is too large")
    reservation = token_reservation(
        method="POST", body=body, payload=payload,
        content_type="application/json", default=settings.default_token_reservation,
    )
    if not db.reserve_tokens(user["id"], reservation):
        raise HTTPException(status_code=402, detail="账户剩余 Token 额度不足，请联系管理员")
    try:
        return await proxy_request(
            request=request, path=path, body=body, payload=payload,
            key=key, client=client, settings=settings, db=db, reserved_tokens=reservation,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="模型响应超时，请稍后重试") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="无法连接上游模型，请稍后重试") from exc
