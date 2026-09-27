import uuid

from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUser, DatabaseDep
from app.core.security import hash_key, new_gateway_key
from app.schemas.keys import KeyCreate, KeyCreated, KeyUpdate, KeyView

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.get("", response_model=list[KeyView])
def list_keys(user: CurrentUser, db: DatabaseDep) -> list[dict]:
    return db.list_keys(user["id"])


@router.post("", response_model=KeyCreated, status_code=201)
def create_key(data: KeyCreate, user: CurrentUser, db: DatabaseDep) -> dict:
    if not db.user_can_use_model(user["id"], data.provider_id, data.model_id, user["is_admin"]):
        raise HTTPException(status_code=403, detail="This model is not assigned to your account")
    value = new_gateway_key()
    row = db.create_key(
        key_id=str(uuid.uuid4()),
        name=data.name.strip(),
        key_hash=hash_key(value),
        prefix=value[:10],
        owner_id=user["id"],
        provider_id=data.provider_id,
        model_id=data.model_id,
        rpm=user["rpm_limit"],
        token_limit=user["token_limit"],
    )
    return {**row, "key": value}


@router.patch("/{key_id}", response_model=KeyView)
def update_key(key_id: str, data: KeyUpdate, user: CurrentUser, db: DatabaseDep) -> dict:
    row = db.update_key(
        key_id,
        owner_id=user["id"],
        enabled=data.enabled,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Key not found")
    return row


@router.delete("/{key_id}", status_code=204)
def revoke_key(key_id: str, user: CurrentUser, db: DatabaseDep) -> None:
    if not db.revoke_key(key_id, user["id"]):
        raise HTTPException(status_code=404, detail="Key not found")
