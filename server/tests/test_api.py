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


if __name__ == "__main__":
    unittest.main()
