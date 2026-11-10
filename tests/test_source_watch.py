import unittest

from app.main import source_file_ready


class SourceWatchTests(unittest.TestCase):
    def test_waits_until_file_is_old_enough(self):
        self.assertFalse(source_file_ready(100, 970, now=999, minimum_age_seconds=30))
        self.assertTrue(source_file_ready(100, 969, now=1000, minimum_age_seconds=30))

    def test_rejects_empty_or_invalid_file_metadata(self):
        self.assertFalse(source_file_ready(0, 900, now=1000))
        self.assertFalse(source_file_ready(-1, 900, now=1000))
        self.assertFalse(source_file_ready(100, "not-a-time", now=1000))


if __name__ == "__main__":
    unittest.main()
