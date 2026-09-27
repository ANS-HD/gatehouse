from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUser, DatabaseDep, SettingsDep
from app.core.security import encrypt_secret
from app.schemas.providers import ProviderCreate, ProviderUpdate, ProviderView

router = APIRouter(prefix="/api/providers", tags=["providers"])


def require_admin(user: dict) -> None:
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Administrator access is required")


def require_secure_url(url: object, settings: SettingsDep) -> None:
    if getattr(url, "scheme", "") != "https" and not settings.allow_insecure_upstreams:
        raise HTTPException(
            status_code=400,
            detail="Upstream Base URL must use HTTPS",
        )


@router.get("", response_model=list[ProviderView])
def list_providers(user: CurrentUser, db: DatabaseDep) -> list[dict]:
    return db.list_providers(
        include_disabled=user["is_admin"],
        user_id=None if user["is_admin"] else user["id"],
    )


@router.post("", response_model=ProviderView, status_code=201)
def create_provider(
    data: ProviderCreate,
    user: CurrentUser,
    db: DatabaseDep,
    settings: SettingsDep,
) -> dict:
    require_admin(user)
    require_secure_url(data.base_url, settings)
    row = db.create_provider(
        name=data.name,
        protocol=data.protocol,
        base_url=str(data.base_url),
        api_key_encrypted=encrypt_secret(data.api_key, settings.session_secret.get_secret_value()),
        enabled=data.enabled,
        model_names=data.models,
    )
    if not row:
        raise HTTPException(status_code=409, detail="Provider name already exists")
    return row


@router.patch("/{provider_id}", response_model=ProviderView)
def update_provider(
    provider_id: str,
    data: ProviderUpdate,
    user: CurrentUser,
    db: DatabaseDep,
    settings: SettingsDep,
) -> dict:
    require_admin(user)
    if data.base_url is not None:
        require_secure_url(data.base_url, settings)
    changes = data.model_dump(exclude_unset=True, exclude={"api_key", "models"})
    if data.base_url is not None:
        changes["base_url"] = str(data.base_url)
    if data.api_key is not None:
        changes["api_key_encrypted"] = encrypt_secret(
            data.api_key, settings.session_secret.get_secret_value()
        )
    row = db.update_provider(provider_id, model_names=data.models, **changes)
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found or name already exists")
    return row
