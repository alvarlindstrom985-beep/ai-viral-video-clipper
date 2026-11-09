import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main


class BatchPersistenceTests(unittest.TestCase):
    def test_jobs_survive_reload_and_running_jobs_become_interrupted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "jobs.sqlite3"
            jobs = {
                "a" * 12: {
                    "batch_id": "a" * 12, "job_id": "b" * 12,
                    "status": "running", "stage": "Renderar",
                    "short_count": 8, "long_count": 1, "completed": 2,
                    "total": 27, "results": []
                },
                "c" * 12: {
                    "batch_id": "c" * 12, "job_id": "d" * 12,
                    "status": "completed", "stage": "Klart",
                    "completed": 3, "total": 3, "results": [{"name": "clip.mp4"}]
                }
            }
            with patch.object(main, "BATCH_DB_FILE", database), patch.object(main, "BATCH_JOBS", jobs):
                for batch_id, state in jobs.items():
                    main.save_batch_job(batch_id, state)

                restored = {}
                with patch.object(main, "BATCH_JOBS", restored):
                    main.restore_batch_jobs()

                interrupted = restored["a" * 12]
                self.assertEqual(interrupted["status"], "interrupted")
                self.assertTrue(interrupted["recovered_after_restart"])
                self.assertEqual(interrupted["short_count"], 8)
                self.assertEqual(interrupted["completed"], 2)
                self.assertEqual(restored["c" * 12]["status"], "completed")
                self.assertEqual(restored["c" * 12]["results"][0]["name"], "clip.mp4")

    def test_queued_jobs_are_also_marked_interrupted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "jobs.sqlite3"
            state = {"batch_id": "e" * 12, "status": "queued", "stage": "Väntar"}
            with patch.object(main, "BATCH_DB_FILE", database), patch.object(main, "BATCH_JOBS", {}):
                main.save_batch_job("e" * 12, state)
                restored = {}
                with patch.object(main, "BATCH_JOBS", restored):
                    main.restore_batch_jobs()
                self.assertEqual(restored["e" * 12]["status"], "interrupted")
                self.assertIn("starta om", restored["e" * 12]["error"])


if __name__ == "__main__":
    unittest.main()
