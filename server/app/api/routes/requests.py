import binascii

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUser, DatabaseDep, SettingsDep
from app.core.security import decrypt_secret
from app.schemas.requests import RequestDetailView

router = APIRouter(prefix="/api/requests", tags=["requests"])


def decrypt_optional(value: str | None, secret: str) -> str | None:
    if not value:
        return None
    try:
        return decrypt_secret(value, secret)
    except (ValueError, UnicodeDecodeError, InvalidTag, binascii.Error):
        return None


@router.get("/{request_id}", response_model=RequestDetailView)
def request_detail(
    request_id: int,
    user: CurrentUser,
    db: DatabaseDep,
    settings: SettingsDep,
) -> dict:
    row = db.get_request_detail(request_id, user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    secret = settings.session_secret.get_secret_value()
    row["query_string"] = decrypt_optional(row.pop("query_string_encrypted"), secret) or row.get(
        "query_string"
    )
    for field in (
        "request_headers",
        "request_body",
        "response_headers",
        "response_body",
    ):
        row[field] = decrypt_optional(row.pop(f"{field}_encrypted"), secret)
    return row
