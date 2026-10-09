import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.update(
    {
        "ADMIN_EMAIL": "admin@example.com",
        "ADMIN_PASSWORD": "admin-password",
        "SESSION_SECRET": "test-session-secret-with-at-least-32-characters",
        "DATABASE_PATH": str(Path(tempfile.mkdtemp()) / "api-test.db"),
        "REGISTRATION_ENABLED": "true",
        "REQUEST_TIMEOUT_SECONDS": "1",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        database = Path(os.environ["DATABASE_PATH"])
        for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
            path.unlink(missing_ok=True)
        database.parent.rmdir()

    def login(self, email: str, password: str) -> tuple[str, dict]:
        response = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        return data["token"], data["user"]

    @staticmethod
    def authorization(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_admin_user_lifecycle_and_failed_proxy_logging(self) -> None:
        self.assertEqual(self.client.get("/api/auth/config").json(), {"registration_enabled": True})
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/register",
                json={"email": "short@example.com", "password": "short"},
            ).status_code,
            422,
        )

        admin_token, _ = self.login("admin@example.com", "admin-password")
        admin_headers = self.authorization(admin_token)
        provider_response = self.client.post(
            "/api/providers",
            headers=admin_headers,
            json={
                "name": "Unavailable upstream",
                "protocol": "openai",
                "base_url": "https://127.0.0.1:1/v1",
                "api_key": "upstream-secret",
                "models": ["model-a"],
                "enabled": True,
            },
        )
        self.assertEqual(provider_response.status_code, 201, provider_response.text)
        provider = provider_response.json()
        model_id = provider["models"][0]["id"]

        create_response = self.client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": "managed@example.com",
                "password": "initial-password",
                "enabled": True,
                "rpm_limit": 30,
                "token_limit": 100,
                "model_ids": [model_id],
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        managed = create_response.json()
        self.assertEqual(managed["allowed_model_ids"], [model_id])

        user_token, _ = self.login("managed@example.com", "initial-password")
        user_headers = self.authorization(user_token)
        key_response = self.client.post(
            "/api/keys",
            headers=user_headers,
            json={"name": "test", "provider_id": provider["id"], "model_id": model_id},
        )
        self.assertEqual(key_response.status_code, 201, key_response.text)
        gateway_key = key_response.json()["key"]

        for _ in range(2):
            failed = self.client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {gateway_key}"},
                json={"model": "model-a", "messages": [], "max_tokens": 1},
            )
            self.assertEqual(failed.status_code, 502, failed.text)

        overview = self.client.get("/api/overview", headers=user_headers).json()
        self.assertEqual(overview["summary"]["errors_24h"], 2)
        self.assertEqual(overview["summary"]["tokens_24h"], 0)
        detail = self.client.get(
            f"/api/requests/{overview['recent'][0]['id']}", headers=user_headers
        ).json()
        self.assertIn('"authorization": "[REDACTED]"', detail["request_headers"])
        self.assertIn('"model": "model-a"', detail["request_body"])

        reset_response = self.client.patch(
            f"/api/admin/users/{managed['id']}",
            headers=admin_headers,
            json={
                "password": "replacement-password",
                "enabled": True,
                "rpm_limit": 30,
                "token_limit": 100,
                "model_ids": [model_id],
            },
        )
        self.assertEqual(reset_response.status_code, 200, reset_response.text)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"email": "managed@example.com", "password": "initial-password"},
            ).status_code,
            401,
        )
        self.login("managed@example.com", "replacement-password")

    def test_codex_session_import_is_encrypted_deduplicated_and_scoped(self) -> None:
        token, _ = self.login("admin@example.com", "admin-password")
        headers = {**self.authorization(token), "Content-Type": "application/x-ndjson"}
        records = [
            {
                "timestamp": "2026-09-28T01:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "session-test-1",
                    "timestamp": "2026-09-28T01:00:00Z",
                    "cwd": "/private/project",
                    "source": "cli",
                },
            },
            {
                "timestamp": "2026-09-28T01:01:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<environment_context>metadata only</environment_context>",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-09-28T01:01:30Z",
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": "turn-test-1"},
            },
            {
                "timestamp": "2026-09-28T01:01:31Z",
                "type": "turn_context",
                "payload": {
                    "turn_id": "turn-test-1",
                    "model": "test-codex-model",
                    "effort": "high",
                    "cwd": "/private/project",
                    "workspace_roots": ["/private/project"],
                    "approval_policy": "on-request",
                    "sandbox_policy": {"type": "workspace-write"},
                    "summary": "Earlier decisions",
                },
            },
            {
                "timestamp": "2026-09-28T01:01:32Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Follow repository rules"}],
                },
            },
            {
                "timestamp": "2026-09-28T01:01:33Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "实现上传功能"}],
                },
            },
            {
                "timestamp": "2026-09-28T01:01:34Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "实现上传功能"},
            },
            {
                "timestamp": "2026-09-28T01:02:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "已经完成"}],
                },
            },
            {
                "timestamp": "2026-09-28T01:03:00Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "call-test-1",
                    "name": "apply_patch",
                    "arguments": "*** Begin Patch",
                },
            },
            {
                "timestamp": "2026-09-28T01:03:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-test-1",
                    "output": "Done!",
                },
            },
            {
                "timestamp": "2026-09-28T01:03:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 60,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                            "total_tokens": 120,
                        },
                        "total_token_usage": {"total_tokens": 120},
                        "model_context_window": 200000,
                    },
                },
            },
            {
                "timestamp": "2026-09-28T01:03:03Z",
                "type": "event_msg",
                "payload": {"type": "task_complete", "turn_id": "turn-test-1"},
            },
        ]
        raw = "\n".join(json.dumps(item, ensure_ascii=False) for item in records).encode()
        first = self.client.post(
            "/api/codex/sessions/import?filename=session.jsonl", headers=headers, content=raw
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "created")
        self.assertEqual(first.json()["session"]["title"], "实现上传功能")
        self.assertEqual(first.json()["session"]["tool_call_count"], 1)
        self.assertEqual(first.json()["session"]["model"], "test-codex-model")
        self.assertEqual(first.json()["session"]["turn_count"], 1)
        self.assertEqual(first.json()["session"]["cached_input_tokens"], 60)

        duplicate = self.client.post(
            "/api/codex/sessions/import?filename=session.jsonl", headers=headers, content=raw
        )
        self.assertEqual(duplicate.json()["status"], "unchanged")
        sessions = self.client.get("/api/codex/sessions", headers=self.authorization(token)).json()
        self.assertTrue(any(item["session_id"] == "session-test-1" for item in sessions))
        detail = self.client.get(
            "/api/codex/sessions/session-test-1", headers=self.authorization(token)
        )
        self.assertEqual(
            [item["role"] for item in detail.json()["messages"]],
            ["system", "developer", "user", "assistant"],
        )
        turn = detail.json()["turns"][0]
        self.assertEqual(turn["effort"], "high")
        self.assertEqual(turn["tool_call_count"], 1)
        self.assertEqual(turn["events"][0]["role"], "developer")
        self.assertEqual(
            [event["role"] for event in turn["events"] if event["kind"] == "message"],
            ["developer", "user", "assistant"],
        )
        self.assertEqual(turn["context"]["summary"], "Earlier decisions")
        self.assertEqual(turn["context"]["sandbox"], "workspace-write")
        self.assertEqual(turn["events"][-1]["output"], "Done!")
        search = self.client.get(
            "/api/codex/sessions?q=已经完成&project=%2Fprivate%2Fproject",
            headers=self.authorization(token),
        )
        self.assertEqual([item["session_id"] for item in search.json()], ["session-test-1"])
        no_match = self.client.get(
            "/api/codex/sessions?q=definitely-not-present", headers=self.authorization(token)
        )
        self.assertEqual(no_match.json(), [])

        with app.state.db.connect() as connection:
            stored = connection.execute(
                "SELECT title_encrypted, transcript_encrypted FROM codex_sessions "
                "WHERE session_id = 'session-test-1'"
            ).fetchone()
        self.assertNotIn("实现上传功能", stored["title_encrypted"])
        self.assertNotIn("已经完成", stored["transcript_encrypted"])

        deleted = self.client.delete(
            "/api/codex/sessions/session-test-1", headers=self.authorization(token)
        )
        self.assertEqual(deleted.status_code, 204)

    def test_codex_upload_token_only_authorizes_imports(self) -> None:
        session_token, _ = self.login("admin@example.com", "admin-password")
        created = self.client.post(
            "/api/codex/upload-token", headers=self.authorization(session_token)
        )
        self.assertEqual(created.status_code, 200, created.text)
        upload_token = created.json()["token"]
        self.assertTrue(upload_token.startswith("clu_"))

        raw = "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-09-28T02:00:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "upload-token-session",
                            "timestamp": "2026-09-28T02:00:00Z",
                            "source": "cli",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-09-28T02:01:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "token upload"}],
                        },
                    }
                ),
            ]
        ).encode()
        imported = self.client.post(
            "/api/codex/sessions/import?filename=token.jsonl",
            headers={
                "Authorization": f"Bearer {upload_token}",
                "Content-Type": "application/x-ndjson",
            },
            content=raw,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(
            self.client.get(
                "/api/codex/sessions", headers=self.authorization(upload_token)
            ).status_code,
            401,
        )

        revoked = self.client.delete(
            "/api/codex/upload-token", headers=self.authorization(session_token)
        )
        self.assertEqual(revoked.status_code, 204)
        rejected = self.client.post(
            "/api/codex/sessions/import?filename=token.jsonl",
            headers={"Authorization": f"Bearer {upload_token}"},
            content=raw,
        )
        self.assertEqual(rejected.status_code, 401)


if __name__ == "__main__":
    unittest.main()
