import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, auth, gateway, health, keys, overview, providers, requests
from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.services.auth import hash_password
from app.services.rate_limit import LoginRateLimiter, RequestRateLimiter
from app.storage.database import Database


async def purge_request_logs(db: Database, retention_days: int) -> None:
    while True:
        await asyncio.sleep(6 * 60 * 60)
        await asyncio.to_thread(db.purge_request_details, retention_days)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize()
    db.purge_request_details(settings.detailed_log_retention_days)
    purge_task = asyncio.create_task(purge_request_logs(db, settings.detailed_log_retention_days))
    admin = db.ensure_admin(
        settings.admin_email,
        hash_password(settings.admin_password.get_secret_value()),
    )
    db.assign_unowned_keys(admin["id"])
    upstream_key = settings.openai_api_key.get_secret_value()
    if upstream_key:
        db.ensure_default_provider(
            name="OpenAI",
            base_url=settings.openai_base_url,
            api_key_encrypted=encrypt_secret(
                upstream_key, settings.session_secret.get_secret_value()
            ),
        )
    app.state.db = db
    app.state.request_limiter = RequestRateLimiter()
    app.state.login_limiter = LoginRateLimiter()
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_seconds, connect=15),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        trust_env=False,
    )
    yield
    purge_task.cancel()
    with suppress(asyncio.CancelledError):
        await purge_task
    await app.state.http_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Gatehouse",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "x-api-key",
            "anthropic-version",
            "anthropic-beta",
        ],
    )
    for router in (
        health.router,
        auth.router,
        admin.router,
        overview.router,
        providers.router,
        keys.router,
        requests.router,
        gateway.router,
    ):
        app.include_router(router)
    return app


app = create_app()
