import unittest

from pathlib import Path

from app.main import resolve_source_inbox, source_file_ready


class SourceWatchTests(unittest.TestCase):
    def test_explicit_inbox_setting_takes_priority(self):
        resolved = resolve_source_inbox(
            {"CLIPPER_SOURCE_INBOX": "~/custom/inbox", "OneDrive": "/cloud/OneDrive"},
            root=Path("/app")
        )
        self.assertEqual(resolved, Path("~/custom/inbox").expanduser())

    def test_detects_personal_onedrive_sync_folder(self):
        resolved = resolve_source_inbox({"OneDrive": "/users/test/OneDrive"}, root=Path("/app"))
        self.assertEqual(resolved, Path("/users/test/OneDrive/AI Viral Video Clipper/Inbox"))

    def test_detects_business_onedrive_when_personal_missing(self):
        resolved = resolve_source_inbox(
            {"OneDriveCommercial": "/users/test/OneDrive - Company"},
            root=Path("/app")
        )
        self.assertEqual(resolved, Path("/users/test/OneDrive - Company/AI Viral Video Clipper/Inbox"))

    def test_falls_back_to_local_inbox(self):
        self.assertEqual(resolve_source_inbox({}, root=Path("/app")), Path("/app/source_inbox"))


    def test_waits_until_file_is_old_enough(self):
        self.assertFalse(source_file_ready(100, 970, now=999, minimum_age_seconds=30))
        self.assertTrue(source_file_ready(100, 969, now=1000, minimum_age_seconds=30))

    def test_rejects_empty_or_invalid_file_metadata(self):
        self.assertFalse(source_file_ready(0, 900, now=1000))
        self.assertFalse(source_file_ready(-1, 900, now=1000))
        self.assertFalse(source_file_ready(100, "not-a-time", now=1000))


if __name__ == "__main__":
    unittest.main()
