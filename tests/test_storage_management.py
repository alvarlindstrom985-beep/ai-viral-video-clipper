import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main


class StorageManagementTests(unittest.TestCase):
    def test_cleanup_preview_only_selects_old_known_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            outputs = root / "outputs"
            uploads.mkdir()
            outputs.mkdir()
            old_time = time.time() - 45 * 86400

            old_upload = uploads / ("a" * 12 + ".mp4")
            old_output = outputs / ("b" * 12 + "_clip_1.mp4")
            protected_output = outputs / ("d" * 12 + "_short_01_v1.mp4")
            performance = outputs / "performance.json"
            database = outputs / "batch_jobs.sqlite3"
            unknown = outputs / "keep-this.log"
            for path in (old_upload, old_output, protected_output, performance, database, unknown):
                path.write_bytes(b"sample")
            for path in (old_upload, old_output, protected_output):
                os.utime(path, (old_time, old_time))

            jobs = {
                "c" * 12: {"batch_id": "c" * 12, "job_id": "d" * 12, "status": "interrupted"}
            }
            with patch.object(main, "UPLOADS", uploads), \
                 patch.object(main, "OUTPUTS", outputs), \
                 patch.object(main, "BATCH_JOBS", jobs):
                candidates = main.storage_cleanup_candidates(now=time.time())
                names = {item["path"].name for item in candidates}
                self.assertEqual(names, {old_upload.name, old_output.name})
                self.assertTrue(protected_output.exists())
                self.assertTrue(performance.exists())
                self.assertTrue(database.exists())
                self.assertTrue(unknown.exists())

    def test_cleanup_preview_does_not_delete_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            outputs = root / "outputs"
            uploads.mkdir()
            outputs.mkdir()
            old_file = outputs / ("e" * 12 + "_export.mp4")
            old_file.write_bytes(b"old")
            old_time = time.time() - 45 * 86400
            os.utime(old_file, (old_time, old_time))
            with patch.object(main, "UPLOADS", uploads), \
                 patch.object(main, "OUTPUTS", outputs), \
                 patch.object(main, "BATCH_JOBS", {}):
                result = main.cleanup_old_storage(dry_run=True)
                self.assertTrue(result["dry_run"])
                self.assertEqual(result["deleted_count"], 0)
                self.assertTrue(old_file.exists())
                self.assertEqual(len(result["candidates"]), 1)

    def test_stale_interrupted_job_no_longer_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            outputs = root / "outputs"
            uploads.mkdir()
            outputs.mkdir()
            old_file = outputs / ("f" * 12 + "_render.mp4")
            old_file.write_bytes(b"old")
            old_time = time.time() - 45 * 86400
            os.utime(old_file, (old_time, old_time))
            stale_state = {
                "batch_id": "f" * 12, "job_id": "1" * 12,
                "status": "interrupted",
                "updated_at": main.datetime.fromtimestamp(old_time, main.timezone.utc).isoformat()
            }
            with (
                patch.object(main, "UPLOADS", uploads),
                patch.object(main, "OUTPUTS", outputs),
                patch.object(main, "BATCH_JOBS", {"f" * 12: stale_state}),
            ):
                self.assertIn(old_file, [item["path"] for item in candidates])

    def test_disk_guard_rejects_upload_when_reserve_would_be_breached(self):
        usage = type("Usage", (), {"free": main.MIN_FREE_DISK_BYTES + 10})()
        with patch.object(main.shutil, "disk_usage", return_value=usage):
            with self.assertRaises(main.HTTPException) as raised:
                main.ensure_upload_space(11)
        self.assertEqual(raised.exception.status_code, 507)


if __name__ == "__main__":
    unittest.main()
