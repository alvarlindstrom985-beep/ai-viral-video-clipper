import unittest

from app.main import normalize_onedrive_video_item


class OneDriveMetadataTests(unittest.TestCase):
    def test_accepts_supported_video_metadata(self):
        item = {
            "id": "drive-item-123",
            "name": "stream-recording.MP4",
            "size": 1024,
            "file": {"mimeType": "video/mp4"},
            "lastModifiedDateTime": "2026-11-10T08:00:00Z",
        }
        self.assertEqual(
            normalize_onedrive_video_item(item),
            {
                "id": "drive-item-123",
                "name": "stream-recording.MP4",
                "size_bytes": 1024,
                "modified_at": "2026-11-10T08:00:00Z",
            },
        )

    def test_rejects_folders_and_unsupported_files(self):
        self.assertIsNone(normalize_onedrive_video_item({"id": "folder", "name": "Inbox", "folder": {}}))
        self.assertIsNone(normalize_onedrive_video_item({
            "id": "document", "name": "notes.txt", "size": 20, "file": {}
        }))

    def test_rejects_missing_ids_invalid_sizes_and_oversized_files(self):
        base = {"name": "clip.mp4", "size": 100, "file": {}}
        self.assertIsNone(normalize_onedrive_video_item(base))
        self.assertIsNone(normalize_onedrive_video_item({**base, "id": "x", "size": "unknown"}))
        self.assertIsNone(normalize_onedrive_video_item({**base, "id": "x", "size": 0}))
        self.assertIsNone(normalize_onedrive_video_item({**base, "id": "x", "size": 2 * 1024**3 + 1}))


if __name__ == "__main__":
    unittest.main()
