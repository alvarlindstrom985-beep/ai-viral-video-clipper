import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.main import (
    get_source_authorization,
    normalize_source_authorization,
    save_source_authorizations,
)


class SourceAuthorizationTests(unittest.TestCase):
    def test_accepts_owner_confirmation(self):
        result = normalize_source_authorization("My own channel", "owner")
        self.assertEqual(result["rights_holder"], "My own channel")
        self.assertEqual(result["permission_basis"], "owner")
        self.assertIn("confirmed_at", result)

    def test_accepts_permission_and_valid_source_url(self):
        result = normalize_source_authorization(
            "Creator name", "written_permission", "https://example.com/permission"
        )
        self.assertEqual(result["source_url"], "https://example.com/permission")

    def test_rejects_missing_rights_holder_or_unknown_basis(self):
        with self.assertRaises(ValueError):
            normalize_source_authorization("", "owner")
        with self.assertRaises(ValueError):
            normalize_source_authorization("Creator", "trust_me")

    def test_rejects_non_http_source_url(self):
        with self.assertRaises(ValueError):
            normalize_source_authorization("Creator", "license", "file:///private/file")

    def test_authorization_is_bound_to_exact_file_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mp4"
            source.write_bytes(b"first version")
            fingerprint = __import__("hashlib").sha256(b"first version").hexdigest()
            record = {"rights_holder": "Creator", "permission_basis": "written_permission"}
            with patch("app.main.SOURCE_AUTHORIZATION_FILE", Path(directory) / "authorizations.json"):
                save_source_authorizations({fingerprint: record})
                self.assertEqual(get_source_authorization(source), record)
                source.write_bytes(b"changed version")
                self.assertIsNone(get_source_authorization(source))


if __name__ == "__main__":
    unittest.main()
