import unittest

from app.main import list_onedrive_video_items, normalize_onedrive_video_item


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

    def test_lists_videos_across_graph_pages(self):
        calls = []
        pages = [
            {"value": [{"id": "one", "name": "one.mp4", "size": 100, "file": {"mimeType": "video/mp4"}}],
             "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/drive/root/children?$skiptoken=abc"},
            {"value": [{"id": "two", "name": "two.mov", "size": 200, "file": {"mimeType": "video/quicktime"}}]},
        ]

        def fetcher(url, token):
            calls.append(url)
            return pages[len(calls) - 1]

        initial = "https://graph.microsoft.com/v1.0/me/drive/root/children?$top=100"
        files, has_more = list_onedrive_video_items("token", initial, fetcher=fetcher)
        self.assertEqual([item["id"] for item in files], ["one", "two"])
        self.assertFalse(has_more)
        self.assertEqual(len(calls), 2)

    def test_rejects_untrusted_graph_next_link(self):
        def fetcher(url, token):
            return {"value": [], "@odata.nextLink": "https://example.com/steal"}

        with self.assertRaises(Exception):
            list_onedrive_video_items(
                "token", "https://graph.microsoft.com/v1.0/me/drive/root/children",
                fetcher=fetcher,
            )

    def test_stops_at_page_limit_and_reports_more_results(self):
        def fetcher(url, token):
            return {"value": [], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/drive/root/children?$skip=next"}

        files, has_more = list_onedrive_video_items(
            "token", "https://graph.microsoft.com/v1.0/me/drive/root/children",
            fetcher=fetcher, max_pages=2,
        )
        self.assertEqual(files, [])
        self.assertTrue(has_more)

    def test_rejects_missing_ids_invalid_sizes_and_oversized_files(self):
        base = {"name": "clip.mp4", "size": 100, "file": {}}
        self.assertIsNone(normalize_onedrive_video_item(base))
        self.assertIsNone(normalize_onedrive_video_item({**base, "id": "x", "size": "unknown"}))
        self.assertIsNone(normalize_onedrive_video_item({**base, "id": "x", "size": 0}))
        self.assertIsNone(normalize_onedrive_video_item({**base, "id": "x", "size": 2 * 1024**3 + 1}))


if __name__ == "__main__":
    unittest.main()
