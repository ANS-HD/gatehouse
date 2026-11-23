import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_session, encrypt_secret
from app.services.auth import verify_password

SECRET = "test-session-secret-with-at-least-32-characters"


class RegistrationAndPaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "admin-password",
            "SESSION_SECRET": SECRET,
            "DATABASE_PATH": str(Path(self.directory.name) / "pagination.db"),
            "OPENAI_API_KEY": "",
            "REGISTRATION_ENABLED": "true",
        })
        self.environment.start()
        get_settings.cache_clear()
        from app.main import create_app

        self.app = create_app()
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()
        self.db = self.app.state.db
        self.user = self.db.create_user("reader@example.com", "unused-hash")
        self.other = self.db.create_user("other@example.com", "unused-hash")
        assert self.user and self.other
        self.headers = self.authorization(self.user)

    def tearDown(self) -> None:
        self.context.__exit__(None, None, None)
        get_settings.cache_clear()
        self.environment.stop()
        self.directory.cleanup()

    @staticmethod
    def authorization(user: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_session(user['id'], False, SECRET, 3600)}"}

    def test_registration_creates_normalized_account_and_usable_session(self) -> None:
        result = self.client.post("/api/auth/register", json={
            "email": " NewUser@Example.com ", "password": "new-user-password",
        })
        self.assertEqual(result.status_code, 201, result.text)
        session = result.json()
        self.assertEqual(session["user"]["email"], "newuser@example.com")
        self.assertFalse(session["user"]["is_admin"])
        self.assertNotIn("password_hash", session["user"])
        stored = self.db.get_user(session["user"]["id"])
        self.assertTrue(verify_password("new-user-password", stored["password_hash"]))
        headers = {"Authorization": f"Bearer {session['token']}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/providers", headers=headers).json(), [])
        self.assertEqual(self.client.get("/api/requests", headers=headers).json()["total"], 0)
        self.assertEqual(self.client.post("/api/auth/register", json={
            "email": "NEWUSER@example.com", "password": "different-password",
        }).status_code, 409)
        self.assertEqual(self.client.post("/api/auth/login", json={
            "email": "newuser@example.com", "password": "new-user-password",
        }).status_code, 200)

    def test_registration_rejects_invalid_input_and_respects_switch(self) -> None:
        for payload in (
            {"email": "invalid", "password": "valid-password"},
            {"email": "invalid@example.com", "password": "short"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/api/auth/register", json=payload).status_code, 422
                )
        with patch.object(get_settings(), "registration_enabled", False):
            self.assertFalse(self.client.get("/api/auth/config").json()["registration_enabled"])
            response = self.client.post("/api/auth/register", json={
                "email": "closed@example.com", "password": "valid-password",
            })
            self.assertEqual(response.status_code, 403)
            self.assertIsNone(self.db.get_user_by_email("closed@example.com"))

    def test_requests_pages_cover_history_and_are_scoped(self) -> None:
        provider = self.db.create_provider(
            name="Test", protocol="openai", base_url="https://example.com/v1",
            api_key_encrypted="encrypted", enabled=True, model_names=["model-a"],
        )
        for user in (self.user, self.other):
            self.db.create_key(
                key_id=user["id"], owner_id=user["id"], provider_id=provider["id"],
                model_id=provider["models"][0]["id"], name="test", key_hash=user["id"],
                prefix="gw_test", rpm=30, token_limit=None,
            )
        for index in range(28):
            self.db.record_request(
                key_id=self.user["id"] if index < 27 else self.other["id"],
                endpoint=f"request-{index}", model="model-a", status_code=200,
                input_tokens=1, output_tokens=1, total_tokens=2, latency_ms=10, error=None,
            )
        collected = []
        for page in range(1, 4):
            result = self.client.get(
                f"/api/requests?page={page}&page_size=10", headers=self.headers,
            ).json()
            self.assertEqual(result["total"], 27)
            self.assertEqual(result["page"], page)
            self.assertEqual(len(result["items"]), 10 if page < 3 else 7)
            collected.extend(item["id"] for item in result["items"])
        self.assertEqual(len(set(collected)), 27)
        self.assertEqual(collected, sorted(collected, reverse=True))
        last = self.client.get("/api/requests?page=99&page_size=20", headers=self.headers).json()
        self.assertEqual((last["page"], len(last["items"])), (2, 7))
        other_id = self.client.get(
            "/api/requests", headers=self.authorization(self.other),
        ).json()["items"][0]["id"]
        self.assertEqual(self.client.get(
            f"/api/requests/{other_id}", headers=self.headers,
        ).status_code, 404)

    def seed_sessions(self, count: int = 505) -> None:
        now = datetime.now(UTC).isoformat()
        transcript = encrypt_secret(json.dumps({
            "type": "event_msg", "payload": {"type": "user_message", "message": "正文关键字"},
        }), SECRET)
        with self.db.connect() as connection:
            connection.executemany(
                """INSERT INTO codex_sessions (
                    owner_id, session_id, source, cwd_encrypted, title_encrypted,
                    transcript_encrypted, content_hash, started_at, ended_at,
                    event_count, message_count, turn_count, tool_call_count, total_tokens,
                    byte_count, imported_at
                ) VALUES (?, ?, 'cli', ?, ?, ?, 'hash', ?, ?, 1, 1, 2, 3, 10, 100, ?)""",
                [(self.user["id"], f"session-{index:04d}",
                  encrypt_secret("/project/a" if index % 2 == 0 else "/project/b", SECRET),
                  encrypt_secret(f"标题 {index}", SECRET), transcript, now, now, now)
                 for index in range(count)],
            )

    def test_codex_pages_search_and_summary_include_all_sessions(self) -> None:
        self.seed_sessions()
        first = self.client.get("/api/codex/sessions?page_size=100", headers=self.headers).json()
        last = self.client.get(
            "/api/codex/sessions?page=6&page_size=100", headers=self.headers,
        ).json()
        self.assertEqual(first["total"], 505)
        self.assertEqual(len(first["items"]), 100)
        self.assertEqual(last["total"], 505)
        self.assertEqual(len(last["items"]), 5)
        self.assertEqual(last["items"][-1]["session_id"], "session-0000")
        self.assertEqual(first["projects"], ["/project/a", "/project/b"])
        self.assertEqual(first["summary"], {
            "sessions": 505, "turns": 1010, "messages": 505, "tools": 1515, "tokens": 5050,
        })
        filtered = self.client.get("/api/codex/sessions", headers=self.headers, params={
            "q": "正文关键字", "project": "/project/a", "page": 3, "page_size": 100,
        }).json()
        self.assertEqual((filtered["total"], len(filtered["items"])), (253, 53))
        self.assertEqual(filtered["summary"], first["summary"])
        self.assertEqual(filtered["projects"], first["projects"])
        renamed = self.client.patch(
            "/api/codex/sessions/session-0000", headers=self.headers, json={"title": "自定义名称"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        search = self.client.get(
            "/api/codex/sessions", headers=self.headers, params={"q": "自定义名称", "page": 99},
        ).json()
        self.assertEqual((search["total"], search["page"]), (1, 1))
        self.assertEqual(search["items"][0]["session_id"], "session-0000")
        other = self.client.get(
            "/api/codex/sessions", headers=self.authorization(self.other),
        ).json()
        self.assertEqual(other["items"], [])
        self.assertEqual(other["projects"], [])
        self.assertEqual(other["summary"]["sessions"], 0)

    def test_codex_delete_restore_and_empty_last_page(self) -> None:
        self.seed_sessions(11)
        self.assertEqual(self.client.delete(
            "/api/codex/sessions/session-0000", headers=self.headers,
        ).status_code, 204)
        page = self.client.get("/api/codex/sessions?page=2", headers=self.headers).json()
        self.assertEqual((page["page"], page["total"]), (1, 10))
        self.assertEqual(page["summary"]["sessions"], 10)
        trash = self.client.get("/api/codex/sessions?deleted=true", headers=self.headers).json()
        self.assertEqual(trash["total"], 1)
        self.assertEqual(trash["items"][0]["session_id"], "session-0000")
        self.assertEqual(trash["projects"], ["/project/a"])
        self.assertEqual(self.client.post(
            "/api/codex/sessions/session-0000/restore", headers=self.headers,
        ).status_code, 204)
        self.assertEqual(self.client.get(
            "/api/codex/sessions?deleted=true&page=99", headers=self.headers,
        ).json()["page"], 1)
        restored = self.client.get("/api/codex/sessions?page=2", headers=self.headers).json()
        self.assertEqual((restored["page"], restored["total"]), (2, 11))

    def test_pagination_requires_authentication_and_valid_bounds(self) -> None:
        for path in ("/api/requests", "/api/codex/sessions"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
                for query in ("page=0", "page=-1", "page_size=0", "page_size=101"):
                    self.assertEqual(self.client.get(
                        f"{path}?{query}", headers=self.headers,
                    ).status_code, 422)
                empty = self.client.get(f"{path}?page=99", headers=self.headers).json()
                self.assertEqual((empty["page"], empty["total"], empty["items"]), (1, 0, []))
