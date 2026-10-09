import base64
import hashlib
import hmac
import json
import secrets
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def hash_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_gateway_key() -> str:
    return f"gw_{secrets.token_urlsafe(32)}"


def new_codex_upload_token() -> str:
    return f"clu_{secrets.token_urlsafe(32)}"


def encrypt_secret(value: str, secret: str) -> str:
    key = hashlib.sha256(secret.encode()).digest()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, value.encode(), None)
    return _encode(nonce + encrypted)


def decrypt_secret(value: str, secret: str) -> str:
    raw = _decode(value)
    key = hashlib.sha256(secret.encode()).digest()
    return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode()


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_session(user_id: str, is_admin: bool, secret: str, ttl: int) -> str:
    payload = _encode(
        json.dumps(
            {"sub": user_id, "admin": is_admin, "exp": int(time.time()) + ttl},
            separators=(",", ":"),
        ).encode()
    )
    signature = _encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def read_session(token: str, secret: str) -> dict | None:
    try:
        payload, signature = token.split(".", 1)
        expected = _encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        data = json.loads(_decode(payload))
        if not hmac.compare_digest(signature, expected) or int(data["exp"]) <= time.time():
            return None
        return data if isinstance(data.get("sub"), str) else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
