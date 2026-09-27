from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Request

from app.core.config import Settings, get_settings
from app.core.security import read_session
from app.services.rate_limit import LoginRateLimiter, RequestRateLimiter
from app.storage.database import Database


def bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_request_limiter(request: Request) -> RequestRateLimiter:
    return request.app.state.request_limiter


def get_login_limiter(request: Request) -> LoginRateLimiter:
    return request.app.state.login_limiter


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Database, Depends(get_database)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    payload = read_session(bearer_token(authorization), settings.session_secret.get_secret_value())
    user = db.get_user(str(payload["sub"])) if payload else None
    if not user:
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    if not user["enabled"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return user


SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[Database, Depends(get_database)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
RequestLimiterDep = Annotated[RequestRateLimiter, Depends(get_request_limiter)]
LoginLimiterDep = Annotated[LoginRateLimiter, Depends(get_login_limiter)]
CurrentUser = Annotated[dict, Depends(get_current_user)]
