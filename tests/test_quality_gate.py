import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main


class RenderQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "render.mp4"
        self.path.write_bytes(b"x" * 12000)

    def tearDown(self):
        self.temp.cleanup()

    def _probe(self, audio=True, width=1080, height=1920, duration=15.0):
        streams = [{"codec_type": "video", "width": width, "height": height}]
        if audio:
            streams.append({"codec_type": "audio"})
        return subprocess.CompletedProcess(
            ["ffprobe"], 0,
            json.dumps({"format": {"duration": str(duration)}, "streams": streams}), ""
        )

    def test_black_freeze_and_near_clipping_are_warnings_not_automatic_rejection(self):
        video_log = (
            "black_start:0 black_end:2.2 "
            "freeze_start:4.0 freeze_end:7.0"
        )
        audio_log = "max_volume: 0.0 dB"
        with (
            patch.object(main, "run_command", return_value=self._probe()),
            patch.object(main.subprocess, "run", side_effect=[
                subprocess.CompletedProcess(["ffmpeg"], 0, "", video_log),
                subprocess.CompletedProcess(["ffmpeg"], 0, "", audio_log)
            ])
        ):
            result = main.inspect_render_quality(self.path, 15, 1080, 1920)

        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["diagnostics"]["black_seconds"], 2.0)
        self.assertGreaterEqual(result["diagnostics"]["freeze_seconds"], 2.0)
        self.assertEqual(result["diagnostics"]["audio_peak_db"], 0.0)
        self.assertTrue(any("svarta bildpartier" in warning for warning in result["warnings"]))
        self.assertTrue(any("frusen bild" in warning for warning in result["warnings"]))
        self.assertTrue(any("Ljudtoppen" in warning for warning in result["warnings"]))

    def test_missing_audio_fails_technical_gate(self):
        with (
            patch.object(main, "run_command", return_value=self._probe(audio=False)),
            patch.object(main.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["ffmpeg"], 0, "", ""
            ))
        ):
            result = main.inspect_render_quality(self.path, 15, 1080, 1920)
        self.assertFalse(result["passed"])
        self.assertIn("Inget ljudspår hittades", result["warnings"])

    def test_wrong_dimensions_fail_technical_gate(self):
        with (
            patch.object(main, "run_command", return_value=self._probe(width=720)),
            patch.object(main.subprocess, "run", side_effect=[
                subprocess.CompletedProcess(["ffmpeg"], 0, "", ""),
                subprocess.CompletedProcess(["ffmpeg"], 0, "", "max_volume: -4.0 dB")
            ])
        ):
            result = main.inspect_render_quality(self.path, 15, 1080, 1920)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
