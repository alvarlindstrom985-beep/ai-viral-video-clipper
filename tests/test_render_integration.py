import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import main


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg and FFprobe are required for render integration tests")
class BatchRenderIntegrationTests(unittest.TestCase):
    def test_synthetic_source_renders_three_valid_variants_with_captions(self):
        job_id = "e2e123456789"
        batch_id = "e2ebatch12345"
        candidate = {
            "start": 0.0,
            "score": 91.0,
            "reason": "Synthetic integration-test highlight",
            "categories": ["GTA-händelse"],
            "matched_phrases": [],
            "rage_score": 0,
            "learning_bonus": 0,
            "rage_phrases": [],
            "hook_score": 0,
            "hook_signals": [],
            "retention_score": 50,
            "retention_label": "Test",
            "retention_reasons": [],
            "retention_components": {},
            "pacing_buckets_active": 1,
            "signal_families": 1,
            "signal_diversity_score": 1,
            "payoff_score": 50,
        }
        transcript = [{"start": 1.0, "end": 3.0, "text": "Synthetic test caption"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            outputs = root / "outputs"
            uploads.mkdir()
            outputs.mkdir()
            source = uploads / f"{job_id}.mp4"
            generated = subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=size=320x240:rate=5",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                "-t", "16", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                "-preset", "ultrafast", "-c:a", "aac", str(source)
            ], capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)

            state = {"status": "queued", "completed": 0, "total": 0, "results": []}
            with (
                patch.object(main, "UPLOADS", uploads),
                patch.object(main, "OUTPUTS", outputs),
                patch.object(main, "BATCH_JOBS", {batch_id: state}),
                patch.object(main, "audio_levels", return_value=[]),
                patch.object(main, "transcribe_audio", return_value=transcript),
                patch.object(main, "analyze_visual_reactions", return_value=None),
                patch.object(main, "score_windows", return_value=[candidate.copy()]),
            ):
                main.render_batch_job(
                    batch_id, job_id, short_count=1, long_count=0,
                    short_length=15, long_length=180,
                    burn_subtitles=True, subtitle_style="classic",
                    caption_mode="sentence"
                )

            self.assertEqual(state["status"], "completed", state.get("error"))
            self.assertEqual(state["completed"], 3)
            self.assertEqual(len(state["results"]), 3)
            self.assertEqual(state["quality_passed"], 3)
            self.assertEqual(state["quality_rejected"], 0)
            self.assertTrue(all(item["subtitles_burned"] for item in state["results"]))
            self.assertTrue(all(item["hook_overlay"] for item in state["results"]))

            for item in state["results"]:
                output = outputs / item["name"]
                self.assertTrue(output.is_file())
                probe = subprocess.run([
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration:stream=codec_type,width,height",
                    "-of", "json", str(output)
                ], capture_output=True, text=True)
                self.assertEqual(probe.returncode, 0, probe.stderr)
                metadata = json.loads(probe.stdout)
                video = next(stream for stream in metadata["streams"]
                             if stream["codec_type"] == "video")
                audio = next(stream for stream in metadata["streams"]
                             if stream["codec_type"] == "audio")
                self.assertEqual((video["width"], video["height"]), (1080, 1920))
                self.assertGreater(float(metadata["format"]["duration"]), 13.0)
                self.assertTrue(audio)

            archive_path = outputs / f"{batch_id}_drafts.zip"
            self.assertTrue(archive_path.is_file())
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                self.assertEqual(sum(name.endswith(".mp4") for name in names), 3)
                self.assertTrue(any(name.endswith(".srt") for name in names))
                self.assertTrue(any(name.endswith(".ass") for name in names))
                self.assertIn("highlight-report.json", names)
                self.assertIn("highlight-report.csv", names)
                csv_report = archive.read("highlight-report.csv").decode("utf-8-sig")
                self.assertIn("selection_reason", csv_report.splitlines()[0])
                self.assertIn("Vald efter grundpoäng", csv_report)


if __name__ == "__main__":
    unittest.main()
