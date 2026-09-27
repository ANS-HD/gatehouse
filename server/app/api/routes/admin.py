from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUser, DatabaseDep
from app.schemas.admin import AdminUserCreate, AdminUserUpdate, AdminUserView
from app.services.auth import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: dict) -> None:
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Administrator access is required")


@router.get("/users", response_model=list[AdminUserView])
def list_users(user: CurrentUser, db: DatabaseDep) -> list[dict]:
    require_admin(user)
    return db.list_users()


@router.post("/users", response_model=AdminUserView, status_code=201)
def create_user(
    data: AdminUserCreate,
    user: CurrentUser,
    db: DatabaseDep,
) -> dict:
    require_admin(user)
    row = db.create_managed_user(
        email=data.email,
        password_hash=hash_password(data.password),
        enabled=data.enabled,
        rpm_limit=data.rpm_limit,
        token_limit=data.token_limit,
        model_ids=data.model_ids,
    )
    if not row:
        raise HTTPException(status_code=409, detail="Email or model assignment is invalid")
    return row


@router.patch("/users/{user_id}", response_model=AdminUserView)
def update_user(
    user_id: str,
    data: AdminUserUpdate,
    user: CurrentUser,
    db: DatabaseDep,
) -> dict:
    require_admin(user)
    row = db.update_user(
        user_id,
        enabled=data.enabled,
        rpm_limit=data.rpm_limit,
        token_limit=data.token_limit,
        model_ids=data.model_ids,
    )
    if not row:
        raise HTTPException(status_code=400, detail="User or model assignment is invalid")
    if data.password:
        db.set_user_password(user_id, hash_password(data.password))
    return row
