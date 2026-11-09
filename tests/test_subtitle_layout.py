import tempfile
import unittest
from pathlib import Path

from app.main import inspect_ass_layout


def ass_document(width=1080, height=1920, font_size=58, margin_l=70,
                 margin_r=70, margin_v=150, text="A short caption"):
    return "\n".join([
        "[Script Info]", f"PlayResX: {width}", f"PlayResY: {height}",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,1,0,1,4,1,2,{margin_l},{margin_r},{margin_v},1",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{text}", ""
    ])


class SubtitleLayoutTests(unittest.TestCase):
    def test_valid_ass_layout_has_no_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            path.write_text(ass_document(), encoding="utf-8")
            result = inspect_ass_layout(path, 1080, 1920)
        self.assertTrue(result["checked"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["canvas"], {"width": 1080, "height": 1920})

    def test_mismatched_canvas_and_unsafe_margins_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            path.write_text(ass_document(width=1920, height=1080, margin_l=500,
                                         margin_r=500, margin_v=500), encoding="utf-8")
            result = inspect_ass_layout(path, 1080, 1920)
        self.assertTrue(any("bildyta matchar" in warning for warning in result["warnings"]))
        self.assertTrue(any("sidmarginaler" in warning for warning in result["warnings"]))
        self.assertTrue(any("vertikal marginal" in warning for warning in result["warnings"]))

    def test_overwide_caption_line_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            path.write_text(ass_document(text="THIS IS A VERY LONG CAPTION " * 8), encoding="utf-8")
            result = inspect_ass_layout(path, 1080, 1920)
        self.assertTrue(any("för bred" in warning for warning in result["warnings"]))

    def test_bottom_caption_in_interface_safe_zone_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            path.write_text(ass_document(margin_v=80), encoding="utf-8")
            result = inspect_ass_layout(path, 1080, 1920)
        self.assertTrue(any("nedre gränssnittszonen" in warning for warning in result["warnings"]))

    def test_top_hook_too_close_to_edge_is_reported(self):
        document = ass_document(margin_v=30).replace(
            "Alignment, MarginL", "Alignment, MarginL"
        ).replace(",1,0,1,4,1,2,70,70,30,1", ",1,0,1,4,1,8,70,70,30,1")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hook.ass"
            path.write_text(document, encoding="utf-8")
            result = inspect_ass_layout(path, 1080, 1920)
        self.assertTrue(any("övre gränssnittszonen" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()

