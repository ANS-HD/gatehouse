import binascii
import json
from typing import Annotated

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.dependencies import CurrentUser, DatabaseDep, SettingsDep, bearer_token
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    hash_key,
    new_codex_upload_token,
    read_session,
)
from app.schemas.codex_logs import (
    CodexImportResult,
    CodexSessionDetail,
    CodexSessionRename,
    CodexSessionView,
    CodexUploadTokenCreated,
    CodexUploadTokenView,
)
from app.services.codex_logs import (
    InvalidCodexLog,
    context_from_transcript,
    messages_from_transcript,
    parse_codex_log,
    tool_calls_from_transcript,
)

router = APIRouter(prefix="/api/codex/sessions", tags=["codex-logs"])
token_router = APIRouter(prefix="/api/codex/upload-token", tags=["codex-logs"])


def get_codex_importer(
    settings: SettingsDep,
    db: DatabaseDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    token = bearer_token(authorization)
    payload = read_session(token, settings.session_secret.get_secret_value())
    user = (
        db.get_user(str(payload["sub"])) if payload else db.use_codex_upload_token(hash_key(token))
    )
    if not user:
        raise HTTPException(status_code=401, detail="Session or Codex upload token is invalid")
    if not user["enabled"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return user


CodexImporter = Annotated[dict, Depends(get_codex_importer)]


def _decrypt(value: str | None, secret: str) -> str | None:
    if not value:
        return None
    try:
        return decrypt_secret(value, secret)
    except (ValueError, UnicodeDecodeError, InvalidTag, binascii.Error):
        return None


def _view(row: dict, secret: str) -> dict:
    result = row.copy()
    cwd_encrypted = result.pop("cwd_encrypted", None)
    title_encrypted = result.pop("title_encrypted", None)
    custom_title_encrypted = result.pop("custom_title_encrypted", None)
    result.pop("transcript_encrypted", None)
    return {
        **result,
        "cwd": _decrypt(cwd_encrypted, secret),
        "title": _decrypt(custom_title_encrypted, secret)
        or _decrypt(title_encrypted, secret)
        or "Untitled Codex session",
    }


@router.get("", response_model=list[CodexSessionView])
def list_sessions(
    user: CurrentUser,
    db: DatabaseDep,
    settings: SettingsDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    project: Annotated[str | None, Query(max_length=500)] = None,
    deleted: bool = False,
) -> list[dict]:
    secret = settings.session_secret.get_secret_value()
    query = q.strip().casefold() if q else None
    project_filter = project.strip().casefold() if project else None
    result = []
    for row in db.list_codex_sessions(user["id"], deleted=deleted):
        cwd = _decrypt(row.get("cwd_encrypted"), secret)
        title = _decrypt(row.get("title_encrypted"), secret) or "Untitled Codex session"
        if project_filter and (cwd or "").casefold() != project_filter:
            continue
        if query:
            transcript = _decrypt(row.get("transcript_encrypted"), secret) or ""
            message_text = "\n".join(
                message["text"] for message in messages_from_transcript(transcript, limit=10_000)
            )
            haystack = "\n".join(
                (title, cwd or "", row.get("model") or "", message_text)
            ).casefold()
            if query not in haystack:
                continue
        result.append(_view(row, secret))
    return result[:100]


@router.post("/import", response_model=CodexImportResult)
async def import_session(
    request: Request,
    user: CodexImporter,
    db: DatabaseDep,
    settings: SettingsDep,
    filename: Annotated[str, Query(min_length=1, max_length=255)] = "session.jsonl",
    content_length: Annotated[int | None, Header()] = None,
) -> dict:
    if content_length is not None and content_length > settings.codex_log_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Log too large"
        )
    raw = await request.body()
    if len(raw) > settings.codex_log_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Log too large"
        )
    try:
        parsed = parse_codex_log(raw, filename)
    except InvalidCodexLog as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    secret = settings.session_secret.get_secret_value()
    data = parsed.__dict__.copy()
    data["derived_version"] = 5
    transcript = data.pop("transcript")
    turns = data.pop("turns")
    cwd = data.pop("cwd")
    title = data.pop("title")
    data["cwd_encrypted"] = encrypt_secret(cwd, secret) if cwd else None
    data["title_encrypted"] = encrypt_secret(title, secret)
    data["transcript_encrypted"] = encrypt_secret(transcript, secret)
    for turn in turns:
        context = turn.pop("context", None)
        turn["context_encrypted"] = (
            encrypt_secret(json.dumps(context, ensure_ascii=False), secret) if context else None
        )
        for event in turn["events"]:
            event["content_encrypted"] = encrypt_secret(
                json.dumps(event, ensure_ascii=False), secret
            )
        data.setdefault("turns", []).append(turn)
    import_status = db.upsert_codex_session(user["id"], data)
    row = db.get_codex_session(user["id"], parsed.session_id)
    assert row is not None
    row.pop("owner_id", None)
    row.pop("transcript_encrypted", None)
    row.pop("content_hash", None)
    return {"status": import_status, "session": _view(row, secret)}


@router.get("/{session_id}", response_model=CodexSessionDetail)
def session_detail(
    session_id: str, user: CurrentUser, db: DatabaseDep, settings: SettingsDep
) -> dict:
    row = db.get_codex_session(user["id"], session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Codex session not found")
    secret = settings.session_secret.get_secret_value()
    transcript = _decrypt(row.pop("transcript_encrypted"), secret)
    if transcript is None:
        raise HTTPException(status_code=500, detail="Unable to decrypt Codex session")
    row.pop("owner_id", None)
    row.pop("content_hash", None)
    turns = db.get_codex_turns(user["id"], session_id)
    for turn in turns:
        context = _decrypt(turn.pop("context_encrypted", None), secret)
        try:
            turn["context"] = json.loads(context) if context else None
        except json.JSONDecodeError:
            turn["context"] = None
        decoded_events = []
        for event in turn.pop("events"):
            content = _decrypt(event.pop("content_encrypted"), secret)
            if content is None:
                continue
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                decoded_events.append(decoded)
        turn["events"] = decoded_events
    return {
        **_view(row, secret),
        "messages": messages_from_transcript(transcript),
        "tool_calls": tool_calls_from_transcript(transcript),
        "context": context_from_transcript(transcript),
        "turns": turns,
    }


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    user: CurrentUser,
    db: DatabaseDep,
    permanent: bool = False,
) -> None:
    if not db.delete_codex_session(user["id"], session_id, permanent=permanent):
        raise HTTPException(status_code=404, detail="Codex session not found")


@router.post("/{session_id}/restore", status_code=204)
def restore_session(session_id: str, user: CurrentUser, db: DatabaseDep) -> None:
    if not db.restore_codex_session(user["id"], session_id):
        raise HTTPException(status_code=404, detail="Codex session not found")


@router.patch("/{session_id}", response_model=CodexSessionView)
def rename_session(
    session_id: str,
    body: CodexSessionRename,
    user: CurrentUser,
    db: DatabaseDep,
    settings: SettingsDep,
) -> dict:
    title = body.title.strip() if body.title else None
    if title and len(title) > 160:
        raise HTTPException(status_code=422, detail="Title must be 160 characters or fewer")
    secret = settings.session_secret.get_secret_value()
    encrypted = encrypt_secret(title, secret) if title else None
    if not db.rename_codex_session(user["id"], session_id, encrypted):
        raise HTTPException(status_code=404, detail="Codex session not found")
    row = db.get_codex_session(user["id"], session_id)
    assert row is not None
    row.pop("owner_id", None)
    row.pop("content_hash", None)
    return _view(row, secret)


@token_router.get("", response_model=CodexUploadTokenView | None)
def upload_token_status(user: CurrentUser, db: DatabaseDep) -> dict | None:
    return db.get_codex_upload_token(user["id"])


@token_router.post("", response_model=CodexUploadTokenCreated)
def create_upload_token(user: CurrentUser, db: DatabaseDep) -> dict:
    token = new_codex_upload_token()
    row = db.replace_codex_upload_token(user["id"], hash_key(token), token[:12])
    return {**row, "token": token}


@token_router.delete("", status_code=204)
def revoke_upload_token(user: CurrentUser, db: DatabaseDep) -> None:
    db.revoke_codex_upload_token(user["id"])
