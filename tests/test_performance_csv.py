import unittest

from app.main import normalize_csv_header, parse_csv_metric, candidate_similarity, is_near_duplicate


class YouTubeCsvMetricTests(unittest.TestCase):
    def test_duration_mm_ss(self):
        self.assertEqual(parse_csv_metric("1:23", duration=True), 83)

    def test_duration_hh_mm_ss(self):
        self.assertEqual(parse_csv_metric("1:02:03", duration=True), 3723)

    def test_decimal_comma(self):
        self.assertEqual(parse_csv_metric("72,5%"), 72.5)

    def test_thousands_separator_for_integer(self):
        self.assertEqual(parse_csv_metric("1,234", integer_only=True), 1234)

    def test_swedish_header_normalization(self):
        self.assertEqual(normalize_csv_header("Genomsnittlig visningsprocent (%)"), "genomsnittligvisningsprocent")


class ClipSimilarityTests(unittest.TestCase):
    def test_same_time_window_is_duplicate(self):
        a = {"start": 10, "end": 40, "_similarity_text": "police chase no way"}
        b = {"start": 12, "end": 42, "_similarity_text": "police chase no way"}
        self.assertTrue(is_near_duplicate(a, b))

    def test_similar_overlapping_transcript_is_duplicate(self):
        a = {"start": 10, "end": 40, "_similarity_text": "that was crazy no way"}
        b = {"start": 20, "end": 50, "_similarity_text": "that was crazy no way"}
        self.assertTrue(is_near_duplicate(a, b))

    def test_different_overlapping_moments_can_survive(self):
        a = {"start": 10, "end": 40, "_similarity_text": "police chase"}
        b = {"start": 20, "end": 50, "_similarity_text": "mission complete"}
        self.assertFalse(is_near_duplicate(a, b))

    def test_similarity_reports_time_and_text(self):
        a = {"start": 0, "end": 30, "_similarity_text": "hello there"}
        b = {"start": 5, "end": 35, "_similarity_text": "hello there"}
        result = candidate_similarity(a, b)
        self.assertGreater(result["text_similarity"], 0.9)
        self.assertGreater(result["overlap_ratio"], 0.8)


class RenderQualityTests(unittest.TestCase):
    def test_missing_render_is_rejected(self):
        from pathlib import Path
        from app.main import inspect_render_quality
        result = inspect_render_quality(Path('/missing-quality-test.mp4'), 30, 1080, 1920)
        self.assertFalse(result['passed'])


if __name__ == "__main__":
    unittest.main()
