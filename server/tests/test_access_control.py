import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

from app.services.provider_proxy import Usage, billable_tokens, requested_model
from app.storage.database import Database


class AccessControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.directory.name) / "gateway.db"))
        self.db.initialize()
        self.admin = self.db.ensure_admin("admin@example.com", "hash")
        self.user = self.db.create_user("user@example.com", "hash")
        self.provider = self.db.create_provider(
            name="Test",
            protocol="openai",
            base_url="https://example.com/v1",
            api_key_encrypted="encrypted",
            enabled=True,
            model_names=["model-a", "model-b"],
        )
        assert self.user and self.provider

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_user_only_sees_assigned_models(self) -> None:
        self.assertEqual(self.db.list_providers(user_id=self.user["id"]), [])
        model = self.provider["models"][0]
        updated = self.db.update_user(
            self.user["id"],
            enabled=True,
            rpm_limit=12,
            token_limit=5000,
            model_ids=[model["id"]],
        )
        self.assertEqual(updated["allowed_model_ids"], [model["id"]])
        providers = self.db.list_providers(user_id=self.user["id"])
        self.assertEqual([item["id"] for item in providers[0]["models"]], [model["id"]])

    def test_removed_model_revokes_access_and_disables_keys(self) -> None:
        model = self.provider["models"][0]
        self.db.update_user(
            self.user["id"],
            enabled=True,
            rpm_limit=12,
            token_limit=None,
            model_ids=[model["id"]],
        )
        self.db.create_key(
            key_id="key-id",
            owner_id=self.user["id"],
            provider_id=self.provider["id"],
            model_id=model["id"],
            name="test",
            key_hash=hashlib.sha256(b"gw_test").hexdigest(),
            prefix="gw_test",
            rpm=12,
            token_limit=None,
        )
        self.db.update_provider(self.provider["id"], model_names=["model-b"])
        self.assertEqual(self.db.list_providers(user_id=self.user["id"]), [])
        self.assertFalse(self.db.get_key("key-id", self.user["id"])["enabled"])

    def test_reads_model_from_json_and_multipart(self) -> None:
        self.assertEqual(requested_model({"model": " model-a "}, b"", ""), "model-a")
        body = (
            b'--boundary\r\nContent-Disposition: form-data; name="model"\r\n\r\n'
            b"whisper-1\r\n--boundary--\r\n"
        )
        self.assertEqual(
            requested_model(None, body, "multipart/form-data; boundary=boundary"),
            "whisper-1",
        )

    def test_token_reservations_are_atomic(self) -> None:
        model = self.provider["models"][0]
        self.db.update_user(
            self.user["id"],
            enabled=True,
            rpm_limit=12,
            token_limit=100,
            model_ids=[model["id"]],
        )
        barrier = threading.Barrier(3)
        results: list[bool] = []

        def reserve() -> None:
            barrier.wait()
            results.append(self.db.reserve_tokens(self.user["id"], 60))

        threads = [threading.Thread(target=reserve) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), [False, True])
        self.db.release_token_reservation(self.user["id"], 60)
        self.assertTrue(self.db.reserve_tokens(self.user["id"], 100))

    def test_success_without_usage_charges_reserved_budget(self) -> None:
        self.assertEqual(billable_tokens(Usage(), 200, 2048, None), 2048)
        self.assertEqual(billable_tokens(Usage(), 500, 2048, "failed"), 0)
        self.assertEqual(billable_tokens(Usage(total_tokens=7), 200, 2048, None), 7)


if __name__ == "__main__":
    unittest.main()
