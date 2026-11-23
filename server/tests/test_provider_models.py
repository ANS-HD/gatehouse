import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.core.config import get_settings


class ProviderModelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "ADMIN_EMAIL": "admin@example.com",
                "ADMIN_PASSWORD": "admin-password",
                "SESSION_SECRET": "test-session-secret-with-at-least-32-characters",
                "DATABASE_PATH": str(Path(self.directory.name) / "models.db"),
                "OPENAI_API_KEY": "",
                "ALLOW_INSECURE_UPSTREAMS": "false",
                "REGISTRATION_ENABLED": "true",
            },
        )
        self.environment.start()
        get_settings.cache_clear()
        from app.main import create_app

        self.app = create_app()
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()
        login = self.client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password"},
        )
        self.headers = {"Authorization": f"Bearer {login.json()['token']}"}
        self.payload = {
            "protocol": "openai",
            "base_url": "https://models.example/v1",
            "api_key": "upstream-test-secret",
        }

    def tearDown(self) -> None:
        self.context.__exit__(None, None, None)
        get_settings.cache_clear()
        self.environment.stop()
        self.directory.cleanup()

    def discover(self, **changes):
        return self.client.post(
            "/api/providers/discover-models",
            headers=self.headers,
            json={**self.payload, **changes},
        )

    def test_openai_models_are_normalized_without_saving(self) -> None:
        response = httpx.Response(
            200,
            json={"data": [
                {"id": "qwen-plus"}, {"id": " qwen-flash "}, {"id": "qwen-plus"},
                {"id": ""}, {"id": 123}, None, {"id": "x" * 129},
            ]},
        )
        with patch.object(
            self.app.state.http_client, "get", AsyncMock(return_value=response)
        ) as get:
            result = self.discover(base_url="https://models.example/v1/")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"models": ["qwen-flash", "qwen-plus"]})
        self.assertEqual(get.call_args.args[0], "https://models.example/v1/models")
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], "Bearer upstream-test-secret"
        )
        self.assertFalse(get.call_args.kwargs["follow_redirects"])
        self.assertNotIn("upstream-test-secret", result.text)
        self.assertEqual(self.client.get("/api/providers", headers=self.headers).json(), [])

    def test_only_administrators_can_discover_models(self) -> None:
        registered = self.client.post(
            "/api/auth/register", json={"email": "user@example.com", "password": "user-password"}
        )
        with patch.object(self.app.state.http_client, "get", AsyncMock()) as get:
            for headers, expected in (
                ({}, 401),
                ({"Authorization": f"Bearer {registered.json()['token']}"}, 403),
            ):
                response = self.client.post(
                    "/api/providers/discover-models", headers=headers, json=self.payload
                )
                self.assertEqual(response.status_code, expected)
            get.assert_not_awaited()

    def test_saved_key_is_reused_only_for_original_destination(self) -> None:
        provider = self.client.post(
            "/api/providers",
            headers=self.headers,
            json={**self.payload, "name": "Saved provider", "models": ["existing-model"]},
        ).json()
        with patch.object(
            self.app.state.http_client,
            "get",
            AsyncMock(return_value=httpx.Response(200, json={"data": [{"id": "new-model"}]})),
        ) as get:
            result = self.discover(provider_id=provider["id"], api_key=None)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(
                get.call_args.kwargs["headers"]["Authorization"], "Bearer upstream-test-secret"
            )
            get.reset_mock()
            for changes in (
                {"base_url": "https://different.example/v1"},
                {"protocol": "anthropic"},
            ):
                result = self.discover(provider_id=provider["id"], api_key=None, **changes)
                self.assertEqual(result.status_code, 400, result.text)
            get.assert_not_awaited()
        providers = self.client.get("/api/providers", headers=self.headers).json()
        self.assertEqual([model["name"] for model in providers[0]["models"]], ["existing-model"])

    def test_anthropic_authentication_and_pagination(self) -> None:
        pages = [
            httpx.Response(200, json={
                "data": [{"id": "claude-a"}], "has_more": True, "last_id": "claude-a",
            }),
            httpx.Response(200, json={"data": [{"id": "claude-b"}], "has_more": False}),
        ]
        with patch.object(self.app.state.http_client, "get", AsyncMock(side_effect=pages)) as get:
            result = self.discover(protocol="anthropic")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"models": ["claude-a", "claude-b"]})
        self.assertEqual(get.call_count, 2)
        first, second = get.call_args_list
        self.assertEqual(first.kwargs["headers"]["x-api-key"], "upstream-test-secret")
        self.assertEqual(first.kwargs["headers"]["anthropic-version"], "2023-06-01")
        self.assertNotIn("Authorization", first.kwargs["headers"])
        self.assertEqual(first.kwargs["params"], {"limit": 1000})
        self.assertEqual(second.kwargs["params"], {"limit": 1000, "after_id": "claude-a"})

    def test_invalid_input_does_not_contact_upstream(self) -> None:
        with patch.object(self.app.state.http_client, "get", AsyncMock()) as get:
            for changes, expected in (
                ({"api_key": None}, 400),
                ({"api_key": None, "provider_id": "missing"}, 404),
                ({"base_url": "http://models.example/v1"}, 400),
            ):
                result = self.discover(**changes)
                self.assertEqual(result.status_code, expected, result.text)
            get.assert_not_awaited()

    def test_upstream_errors_are_safe_and_actionable(self) -> None:
        for response, expected in (
            (httpx.Response(401, json={"error": "upstream-test-secret"}), 400),
            (httpx.Response(404), 400),
            (httpx.Response(302, headers={"location": "https://other.example"}), 502),
            (httpx.Response(500), 502),
            (httpx.Response(200, text="invalid json"), 502),
            (httpx.Response(200, json={"models": []}), 502),
            (httpx.Response(200, json={"data": []}), 400),
        ):
            with self.subTest(status=response.status_code, body=response.text):
                with patch.object(
                    self.app.state.http_client, "get", AsyncMock(return_value=response)
                ):
                    result = self.discover()
                self.assertEqual(result.status_code, expected, result.text)
                self.assertNotIn("upstream-test-secret", result.text)
        for error, expected in (
            (httpx.ReadTimeout("timeout"), 504), (httpx.ConnectError("no"), 502)
        ):
            with patch.object(self.app.state.http_client, "get", AsyncMock(side_effect=error)):
                self.assertEqual(self.discover().status_code, expected)
