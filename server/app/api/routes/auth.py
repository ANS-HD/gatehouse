import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import CurrentUser, DatabaseDep, LoginLimiterDep, SettingsDep
from app.core.security import create_session
from app.schemas.admin import AuthConfig, LoginInput, RegisterInput, SessionOutput, UserView
from app.services.auth import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def session_for(user: dict, settings: SettingsDep) -> SessionOutput:
    return SessionOutput(
        token=create_session(
            user["id"],
            user["is_admin"],
            settings.session_secret.get_secret_value(),
            settings.session_ttl_seconds,
        ),
        user=UserView.model_validate(user),
    )


@router.get("/config", response_model=AuthConfig)
def auth_config(settings: SettingsDep) -> dict[str, bool]:
    return {"registration_enabled": settings.registration_enabled}


@router.post("/register", response_model=SessionOutput, status_code=201)
async def register(
    data: RegisterInput,
    request: Request,
    settings: SettingsDep,
    db: DatabaseDep,
    limiter: LoginLimiterDep,
) -> SessionOutput:
    if not settings.registration_enabled:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    limiter_key = f"register:{request.client.host if request.client else 'unknown'}"
    if limiter.blocked(limiter_key):
        raise HTTPException(status_code=429, detail="Too many registration attempts")
    limiter.fail(limiter_key)
    user = db.create_user(data.email, hash_password(data.password))
    if not user:
        raise HTTPException(status_code=409, detail="Email is already registered")
    return session_for(user, settings)


@router.post("/login", response_model=SessionOutput)
async def login(
    data: LoginInput,
    request: Request,
    settings: SettingsDep,
    db: DatabaseDep,
    limiter: LoginLimiterDep,
) -> SessionOutput:
    ip = request.client.host if request.client else "unknown"
    if limiter.blocked(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    user = db.get_user_by_email(data.email)
    if not user or not verify_password(data.password, user["password_hash"]):
        limiter.fail(ip)
        await asyncio.sleep(0.35)
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    if not user["enabled"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    limiter.clear(ip)
    return session_for(user, settings)


@router.get("/me", response_model=UserView)
def current_user(user: CurrentUser) -> dict:
    return user
