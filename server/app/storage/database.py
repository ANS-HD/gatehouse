import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

KEY_COLUMNS = """client_keys.id, client_keys.name, client_keys.provider_id,
providers.name AS provider_name, client_keys.model_id,
provider_models.name AS model_name, client_keys.prefix, client_keys.created_at,
client_keys.last_used_at, users.rpm_limit AS rpm, users.token_limit,
client_keys.tokens_used,
COALESCE((SELECT SUM(owner_keys.tokens_used) FROM client_keys AS owner_keys
WHERE owner_keys.owner_id = client_keys.owner_id), 0) AS account_tokens_used,
client_keys.enabled"""
USER_COLUMNS = """id, email, password_hash, is_admin, enabled, rpm_limit,
token_limit, created_at"""
PROVIDER_COLUMNS = """id, name, protocol, base_url, enabled, created_at,
'已加密' AS key_hint"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def serialize_key(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "enabled": bool(row["enabled"])}


def serialize_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "is_admin": bool(row["is_admin"]),
        "enabled": bool(row["enabled"]),
    }


def serialize_provider(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "enabled": bool(row["enabled"])}


class Database:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    rpm_limit INTEGER NOT NULL DEFAULT 30,
                    token_limit INTEGER,
                    reserved_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    protocol TEXT NOT NULL CHECK (protocol IN ('openai', 'anthropic')),
                    base_url TEXT NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_models (
                    id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(provider_id, name),
                    FOREIGN KEY (provider_id) REFERENCES providers(id)
                );
                CREATE TABLE IF NOT EXISTS user_model_access (
                    user_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, model_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (model_id) REFERENCES provider_models(id)
                );
                CREATE TABLE IF NOT EXISTS client_keys (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    provider_id TEXT,
                    model_id TEXT,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    prefix TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    rpm INTEGER NOT NULL,
                    token_limit INTEGER,
                    tokens_used INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY (owner_id) REFERENCES users(id),
                    FOREIGN KEY (provider_id) REFERENCES providers(id),
                    FOREIGN KEY (model_id) REFERENCES provider_models(id)
                );
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    model TEXT,
                    status_code INTEGER NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL,
                    error TEXT,
                    method TEXT NOT NULL DEFAULT 'POST',
                    query_string TEXT,
                    query_string_encrypted TEXT,
                    request_headers_encrypted TEXT,
                    request_body_encrypted TEXT,
                    response_headers_encrypted TEXT,
                    response_body_encrypted TEXT,
                    detail_truncated INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (key_id) REFERENCES client_keys(id)
                );
                CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at);
                CREATE INDEX IF NOT EXISTS idx_requests_key_id ON requests(key_id);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(client_keys)")}
            if "owner_id" not in columns:
                connection.execute("ALTER TABLE client_keys ADD COLUMN owner_id TEXT")
            if "provider_id" not in columns:
                connection.execute("ALTER TABLE client_keys ADD COLUMN provider_id TEXT")
            if "model_id" not in columns:
                connection.execute("ALTER TABLE client_keys ADD COLUMN model_id TEXT")
            user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
            user_column_definitions = {
                "enabled": "INTEGER NOT NULL DEFAULT 1",
                "rpm_limit": "INTEGER NOT NULL DEFAULT 30",
                "token_limit": "INTEGER",
                "reserved_tokens": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in user_column_definitions.items():
                if name not in user_columns:
                    connection.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
            connection.execute("UPDATE users SET reserved_tokens = 0")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_keys_owner_id ON client_keys(owner_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_keys_provider_id ON client_keys(provider_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_keys_model_id ON client_keys(model_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_provider_models_provider_id "
                "ON provider_models(provider_id)"
            )
            request_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(requests)")
            }
            detail_columns = {
                "method": "TEXT NOT NULL DEFAULT 'POST'",
                "query_string": "TEXT",
                "query_string_encrypted": "TEXT",
                "request_headers_encrypted": "TEXT",
                "request_body_encrypted": "TEXT",
                "response_headers_encrypted": "TEXT",
                "response_body_encrypted": "TEXT",
                "detail_truncated": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in detail_columns.items():
                if name not in request_columns:
                    connection.execute(f"ALTER TABLE requests ADD COLUMN {name} {definition}")

    def ensure_default_provider(
        self, *, name: str, base_url: str, api_key_encrypted: str
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM providers ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row:
                provider_id = row["id"]
            else:
                provider_id = str(uuid.uuid4())
                normalized_url = base_url.rstrip("/")
                if not normalized_url.endswith("/v1"):
                    normalized_url += "/v1"
                connection.execute(
                    """INSERT INTO providers
                    (id, name, protocol, base_url, api_key_encrypted, enabled, created_at)
                    VALUES (?, ?, 'openai', ?, ?, 1, ?)""",
                    (provider_id, name, normalized_url, api_key_encrypted, utcnow()),
                )
            connection.execute(
                "UPDATE client_keys SET provider_id = ? WHERE provider_id IS NULL",
                (provider_id,),
            )
        return self.get_provider(provider_id) or {}

    def list_provider_models(
        self, provider_id: str, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if user_id:
                rows = connection.execute(
                    """SELECT provider_models.id, provider_models.name
                    FROM provider_models JOIN user_model_access
                    ON user_model_access.model_id = provider_models.id
                    WHERE user_model_access.user_id = ?
                    AND provider_models.provider_id = ? AND provider_models.enabled = 1
                    ORDER BY provider_models.name""",
                    (user_id, provider_id),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT id, name FROM provider_models
                    WHERE provider_id = ? AND enabled = 1 ORDER BY name""",
                    (provider_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_providers(
        self, include_disabled: bool = False, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        where = "" if include_disabled else "WHERE enabled = 1"
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT {PROVIDER_COLUMNS} FROM providers {where} ORDER BY created_at"
            ).fetchall()
        providers = []
        for row in rows:
            provider = serialize_provider(dict(row))
            provider["models"] = self.list_provider_models(provider["id"], user_id)
            if user_id and not provider["models"]:
                continue
            providers.append(provider)
        return providers

    def get_provider(self, provider_id: str, include_secret: bool = False) -> dict[str, Any] | None:
        columns = "*" if include_secret else PROVIDER_COLUMNS
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT {columns} FROM providers WHERE id = ?", (provider_id,)
            ).fetchone()
        if not row:
            return None
        provider = serialize_provider(dict(row))
        provider["models"] = self.list_provider_models(provider_id)
        return provider

    @staticmethod
    def _sync_provider_models(
        connection: sqlite3.Connection, provider_id: str, model_names: list[str]
    ) -> None:
        connection.execute(
            "UPDATE provider_models SET enabled = 0 WHERE provider_id = ?", (provider_id,)
        )
        for name in model_names:
            existing = connection.execute(
                "SELECT id FROM provider_models WHERE provider_id = ? AND name = ?",
                (provider_id, name),
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE provider_models SET enabled = 1 WHERE id = ?", (existing["id"],)
                )
            else:
                connection.execute(
                    """INSERT INTO provider_models (id, provider_id, name, enabled, created_at)
                    VALUES (?, ?, ?, 1, ?)""",
                    (str(uuid.uuid4()), provider_id, name, utcnow()),
                )
        disabled_ids = connection.execute(
            "SELECT id FROM provider_models WHERE provider_id = ? AND enabled = 0",
            (provider_id,),
        ).fetchall()
        if disabled_ids:
            ids = [row["id"] for row in disabled_ids]
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"DELETE FROM user_model_access WHERE model_id IN ({placeholders})",
                tuple(ids),
            )
            connection.execute(
                f"UPDATE client_keys SET enabled = 0 WHERE model_id IN ({placeholders})",
                tuple(ids),
            )

    def create_provider(
        self,
        *,
        name: str,
        protocol: str,
        base_url: str,
        api_key_encrypted: str,
        enabled: bool,
        model_names: list[str],
    ) -> dict[str, Any] | None:
        provider_id = str(uuid.uuid4())
        try:
            with self.connect() as connection:
                connection.execute(
                    """INSERT INTO providers
                    (id, name, protocol, base_url, api_key_encrypted, enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        provider_id,
                        name,
                        protocol,
                        base_url.rstrip("/"),
                        api_key_encrypted,
                        int(enabled),
                        utcnow(),
                    ),
                )
                self._sync_provider_models(connection, provider_id, model_names)
                connection.execute(
                    "UPDATE client_keys SET provider_id = ? WHERE provider_id IS NULL",
                    (provider_id,),
                )
        except sqlite3.IntegrityError:
            return None
        return self.get_provider(provider_id)

    def update_provider(
        self, provider_id: str, *, model_names: list[str] | None = None, **changes: Any
    ) -> dict[str, Any] | None:
        current = self.get_provider(provider_id, include_secret=True)
        if not current:
            return None
        allowed = {"name", "protocol", "base_url", "api_key_encrypted", "enabled"}
        values = {
            key: value for key, value in changes.items() if key in allowed and value is not None
        }
        if not values and model_names is None:
            return self.get_provider(provider_id)
        if "enabled" in values:
            values["enabled"] = int(values["enabled"])
        if "base_url" in values:
            values["base_url"] = str(values["base_url"]).rstrip("/")
        try:
            with self.connect() as connection:
                if values:
                    assignments = ", ".join(f"{key} = ?" for key in values)
                    connection.execute(
                        f"UPDATE providers SET {assignments} WHERE id = ?",
                        (*values.values(), provider_id),
                    )
                if model_names is not None:
                    self._sync_provider_models(connection, provider_id, model_names)
        except sqlite3.IntegrityError:
            return None
        return self.get_provider(provider_id)

    def ensure_admin(self, email: str, password_hash: str) -> dict[str, Any]:
        existing = self.get_user_by_email(email)
        if existing:
            with self.connect() as connection:
                connection.execute(
                    """UPDATE users SET password_hash = ?, is_admin = 1, enabled = 1,
                    rpm_limit = 10000, token_limit = NULL WHERE id = ?""",
                    (password_hash, existing["id"]),
                )
            return self.get_user(existing["id"]) or existing
        with self.connect() as connection:
            user_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO users
                (id, email, password_hash, is_admin, enabled, rpm_limit, token_limit, created_at)
                VALUES (?, ?, ?, 1, 1, 10000, NULL, ?)""",
                (user_id, email, password_hash, utcnow()),
            )
        return self.get_user(user_id) or {}

    def assign_unowned_keys(self, owner_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE client_keys SET owner_id = ? WHERE owner_id IS NULL", (owner_id,)
            )

    def create_user(self, email: str, password_hash: str) -> dict[str, Any] | None:
        user_id = str(uuid.uuid4())
        try:
            with self.connect() as connection:
                connection.execute(
                    """INSERT INTO users
                    (id, email, password_hash, is_admin, enabled, rpm_limit,
                     token_limit, created_at)
                    VALUES (?, ?, ?, 0, 1, 30, NULL, ?)""",
                    (user_id, email, password_hash, utcnow()),
                )
        except sqlite3.IntegrityError:
            return None
        return self.get_user(user_id)

    @staticmethod
    def _valid_model_ids(connection: sqlite3.Connection, model_ids: list[str]) -> bool:
        if not model_ids:
            return True
        placeholders = ",".join("?" for _ in model_ids)
        count = connection.execute(
            f"""SELECT COUNT(*) FROM provider_models
            JOIN providers ON providers.id = provider_models.provider_id
            WHERE provider_models.id IN ({placeholders})
            AND provider_models.enabled = 1 AND providers.enabled = 1""",
            tuple(model_ids),
        ).fetchone()[0]
        return count == len(model_ids)

    def create_managed_user(
        self,
        *,
        email: str,
        password_hash: str,
        enabled: bool,
        rpm_limit: int,
        token_limit: int | None,
        model_ids: list[str],
    ) -> dict[str, Any] | None:
        user_id = str(uuid.uuid4())
        unique_model_ids = list(dict.fromkeys(model_ids))
        try:
            with self.connect() as connection:
                if not self._valid_model_ids(connection, unique_model_ids):
                    return None
                connection.execute(
                    """INSERT INTO users
                    (id, email, password_hash, is_admin, enabled, rpm_limit,
                     token_limit, created_at)
                    VALUES (?, ?, ?, 0, ?, ?, ?, ?)""",
                    (
                        user_id,
                        email,
                        password_hash,
                        int(enabled),
                        rpm_limit,
                        token_limit,
                        utcnow(),
                    ),
                )
                connection.executemany(
                    "INSERT INTO user_model_access (user_id, model_id) VALUES (?, ?)",
                    [(user_id, model_id) for model_id in unique_model_ids],
                )
        except sqlite3.IntegrityError:
            return None
        return next((item for item in self.list_users() if item["id"] == user_id), None)

    def set_user_password(self, user_id: str, password_hash: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ? AND is_admin = 0",
                (password_hash, user_id),
            )
        return cursor.rowcount > 0

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return serialize_user(dict(row)) if row else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT {USER_COLUMNS} FROM users WHERE email = ?", (email,)
            ).fetchone()
        return serialize_user(dict(row)) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT {USER_COLUMNS},
                (SELECT COUNT(*) FROM client_keys
                 WHERE client_keys.owner_id = users.id AND client_keys.enabled = 1) AS active_keys,
                COALESCE((SELECT SUM(client_keys.tokens_used) FROM client_keys
                 WHERE client_keys.owner_id = users.id), 0) AS total_tokens,
                (SELECT COUNT(*) FROM requests JOIN client_keys
                 ON client_keys.id = requests.key_id
                 WHERE client_keys.owner_id = users.id) AS requests_count
                FROM users ORDER BY total_tokens DESC, created_at"""
            ).fetchall()
            result = []
            for row in rows:
                user = serialize_user(dict(row))
                access = connection.execute(
                    "SELECT model_id FROM user_model_access WHERE user_id = ? ORDER BY model_id",
                    (user["id"],),
                ).fetchall()
                user["allowed_model_ids"] = [item["model_id"] for item in access]
                result.append(user)
        return result

    def update_user(
        self,
        user_id: str,
        *,
        enabled: bool,
        rpm_limit: int,
        token_limit: int | None,
        model_ids: list[str],
    ) -> dict[str, Any] | None:
        user = self.get_user(user_id)
        if not user or user["is_admin"]:
            return None
        unique_model_ids = list(dict.fromkeys(model_ids))
        with self.connect() as connection:
            if not self._valid_model_ids(connection, unique_model_ids):
                return None
            connection.execute(
                """UPDATE users SET enabled = ?, rpm_limit = ?, token_limit = ?
                WHERE id = ?""",
                (int(enabled), rpm_limit, token_limit, user_id),
            )
            connection.execute("DELETE FROM user_model_access WHERE user_id = ?", (user_id,))
            connection.executemany(
                "INSERT INTO user_model_access (user_id, model_id) VALUES (?, ?)",
                [(user_id, model_id) for model_id in unique_model_ids],
            )
        return next((item for item in self.list_users() if item["id"] == user_id), None)

    def user_can_use_model(
        self, user_id: str, provider_id: str, model_id: str, is_admin: bool
    ) -> bool:
        with self.connect() as connection:
            if is_admin:
                row = connection.execute(
                    """SELECT 1 FROM provider_models JOIN providers
                    ON providers.id = provider_models.provider_id
                    WHERE provider_models.id = ? AND provider_models.provider_id = ?
                    AND provider_models.enabled = 1 AND providers.enabled = 1""",
                    (model_id, provider_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT 1 FROM provider_models JOIN providers
                    ON providers.id = provider_models.provider_id
                    JOIN user_model_access
                    ON user_model_access.model_id = provider_models.id
                    WHERE user_model_access.user_id = ? AND provider_models.id = ?
                    AND provider_models.provider_id = ? AND provider_models.enabled = 1
                    AND providers.enabled = 1""",
                    (user_id, model_id, provider_id),
                ).fetchone()
        return bool(row)

    def reserve_tokens(self, user_id: str, amount: int) -> bool:
        if amount <= 0:
            return True
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT users.token_limit, users.reserved_tokens,
                COALESCE((SELECT SUM(client_keys.tokens_used) FROM client_keys
                WHERE client_keys.owner_id = users.id), 0) AS tokens_used
                FROM users WHERE users.id = ?""",
                (user_id,),
            ).fetchone()
            if not row:
                return False
            if row["token_limit"] is None:
                return True
            if row["tokens_used"] + row["reserved_tokens"] + amount > row["token_limit"]:
                return False
            connection.execute(
                "UPDATE users SET reserved_tokens = reserved_tokens + ? WHERE id = ?",
                (amount, user_id),
            )
        return True

    def release_token_reservation(self, user_id: str, amount: int) -> None:
        if amount <= 0:
            return
        with self.connect() as connection:
            connection.execute(
                """UPDATE users SET reserved_tokens = MAX(reserved_tokens - ?, 0)
                WHERE id = ?""",
                (amount, user_id),
            )

    def list_keys(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT {KEY_COLUMNS} FROM client_keys
                JOIN providers ON providers.id = client_keys.provider_id
                LEFT JOIN provider_models ON provider_models.id = client_keys.model_id
                JOIN users ON users.id = client_keys.owner_id
                WHERE client_keys.owner_id = ? ORDER BY client_keys.created_at DESC""",
                (owner_id,),
            ).fetchall()
        return [serialize_key(dict(row)) for row in rows]

    def create_key(
        self,
        *,
        key_id: str,
        owner_id: str,
        provider_id: str,
        model_id: str,
        name: str,
        key_hash: str,
        prefix: str,
        rpm: int,
        token_limit: int | None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO client_keys
                (id, owner_id, provider_id, model_id, name, key_hash, prefix, created_at,
                 rpm, token_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key_id,
                    owner_id,
                    provider_id,
                    model_id,
                    name,
                    key_hash,
                    prefix,
                    utcnow(),
                    rpm,
                    token_limit,
                ),
            )
        return self.get_key(key_id, owner_id) or {}

    def get_key(self, key_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""SELECT {KEY_COLUMNS} FROM client_keys
                JOIN providers ON providers.id = client_keys.provider_id
                LEFT JOIN provider_models ON provider_models.id = client_keys.model_id
                JOIN users ON users.id = client_keys.owner_id
                WHERE client_keys.id = ? AND owner_id = ?""",
                (key_id, owner_id),
            ).fetchone()
        return serialize_key(dict(row)) if row else None

    def get_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT client_keys.*, providers.name AS provider_name,
                providers.protocol AS provider_protocol,
                providers.base_url AS provider_base_url,
                providers.api_key_encrypted AS provider_api_key_encrypted,
                providers.enabled AS provider_enabled,
                provider_models.name AS model_name,
                provider_models.enabled AS model_enabled,
                users.enabled AS owner_enabled,
                users.rpm_limit AS owner_rpm_limit,
                users.token_limit AS owner_token_limit,
                COALESCE((SELECT SUM(owner_keys.tokens_used) FROM client_keys AS owner_keys
                WHERE owner_keys.owner_id = client_keys.owner_id), 0) AS owner_tokens_used
                FROM client_keys JOIN providers ON providers.id = client_keys.provider_id
                LEFT JOIN provider_models ON provider_models.id = client_keys.model_id
                JOIN users ON users.id = client_keys.owner_id
                WHERE client_keys.key_hash = ?""",
                (key_hash,),
            ).fetchone()
        return dict(row) if row else None

    def update_key(
        self,
        key_id: str,
        *,
        owner_id: str,
        enabled: bool | None,
    ) -> dict[str, Any] | None:
        current = self.get_key(key_id, owner_id)
        if not current:
            return None
        with self.connect() as connection:
            connection.execute(
                "UPDATE client_keys SET enabled = ? WHERE id = ? AND owner_id = ?",
                (
                    int(enabled if enabled is not None else current["enabled"]),
                    key_id,
                    owner_id,
                ),
            )
        return self.get_key(key_id, owner_id)

    def revoke_key(self, key_id: str, owner_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE client_keys SET enabled = 0 WHERE id = ? AND owner_id = ?",
                (key_id, owner_id),
            )
        return cursor.rowcount > 0

    def record_request(
        self,
        *,
        key_id: str,
        endpoint: str,
        model: str | None,
        status_code: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        latency_ms: int,
        error: str | None,
        method: str = "POST",
        query_string: str | None = None,
        query_string_encrypted: str | None = None,
        request_headers_encrypted: str | None = None,
        request_body_encrypted: str | None = None,
        response_headers_encrypted: str | None = None,
        response_body_encrypted: str | None = None,
        detail_truncated: bool = False,
    ) -> None:
        now = utcnow()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO requests
                (key_id, endpoint, model, status_code, input_tokens, output_tokens,
                 total_tokens, latency_ms, error, method, query_string,
                 query_string_encrypted,
                 request_headers_encrypted, request_body_encrypted,
                 response_headers_encrypted, response_body_encrypted,
                 detail_truncated, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key_id,
                    endpoint,
                    model,
                    status_code,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    latency_ms,
                    error,
                    method,
                    query_string,
                    query_string_encrypted,
                    request_headers_encrypted,
                    request_body_encrypted,
                    response_headers_encrypted,
                    response_body_encrypted,
                    int(detail_truncated),
                    now,
                ),
            )
            connection.execute(
                """UPDATE client_keys
                SET tokens_used = tokens_used + ?, last_used_at = ? WHERE id = ?""",
                (total_tokens, now, key_id),
            )

    def get_request_detail(self, request_id: int, owner_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT requests.*, client_keys.name AS key_name,
                providers.name AS provider_name
                FROM requests
                JOIN client_keys ON client_keys.id = requests.key_id
                JOIN providers ON providers.id = client_keys.provider_id
                WHERE requests.id = ? AND client_keys.owner_id = ?""",
                (request_id, owner_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["detail_truncated"] = bool(result["detail_truncated"])
        return result

    def purge_request_details(self, retention_days: int) -> None:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self.connect() as connection:
            connection.execute(
                """UPDATE requests SET
                query_string_encrypted = NULL,
                request_headers_encrypted = NULL,
                request_body_encrypted = NULL,
                response_headers_encrypted = NULL,
                response_body_encrypted = NULL
                WHERE created_at < ? AND (
                    request_headers_encrypted IS NOT NULL OR
                    query_string_encrypted IS NOT NULL OR
                    request_body_encrypted IS NOT NULL OR
                    response_headers_encrypted IS NOT NULL OR
                    response_body_encrypted IS NOT NULL
                )""",
                (cutoff,),
            )

    def overview(self, owner_id: str) -> dict[str, Any]:
        since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        since_7d = (datetime.now(UTC) - timedelta(days=6)).date().isoformat()
        with self.connect() as connection:
            summary = dict(
                connection.execute(
                    """SELECT
                    (SELECT COUNT(*) FROM client_keys
                     WHERE owner_id = ? AND enabled = 1) AS active_keys,
                    COUNT(requests.id) AS requests_24h,
                    COALESCE(SUM(requests.total_tokens), 0) AS tokens_24h,
                    COALESCE(SUM(CASE WHEN requests.status_code >= 400 THEN 1 ELSE 0 END), 0)
                        AS errors_24h
                    FROM requests JOIN client_keys ON client_keys.id = requests.key_id
                    WHERE client_keys.owner_id = ? AND requests.created_at >= ?""",
                    (owner_id, owner_id, since_24h),
                ).fetchone()
            )
            recent = [
                dict(row)
                for row in connection.execute(
                    """SELECT requests.id, client_keys.name AS key_name, endpoint, model,
                    providers.name AS provider_name, status_code, total_tokens, latency_ms,
                    error, requests.created_at
                    FROM requests JOIN client_keys ON client_keys.id = requests.key_id
                    JOIN providers ON providers.id = client_keys.provider_id
                    WHERE client_keys.owner_id = ?
                    ORDER BY requests.id DESC LIMIT 12""",
                    (owner_id,),
                ).fetchall()
            ]
            daily = [
                dict(row)
                for row in connection.execute(
                    """SELECT substr(requests.created_at, 1, 10) AS date,
                    COUNT(*) AS requests, COALESCE(SUM(requests.total_tokens), 0) AS tokens
                    FROM requests JOIN client_keys ON client_keys.id = requests.key_id
                    WHERE client_keys.owner_id = ? AND requests.created_at >= ?
                    GROUP BY date ORDER BY date""",
                    (owner_id, since_7d),
                ).fetchall()
            ]
        return {"summary": summary, "recent": recent, "daily": daily}
