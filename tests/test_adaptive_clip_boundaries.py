import unittest

from app.main import optimize_clip_boundaries


class AdaptiveClipBoundaryTests(unittest.TestCase):
    def test_trims_leading_and_trailing_silence(self):
        transcript = [
            {"start": 3.0, "end": 6.0, "text": "setup"},
            {"start": 12.0, "end": 15.0, "text": "reaction"},
            {"start": 21.0, "end": 24.0, "text": "aftermath"},
        ]
        result = optimize_clip_boundaries(0, 30, transcript, [{"time": 13, "kind": "speech"}])
        self.assertAlmostEqual(result["start"], 2.3)
        self.assertAlmostEqual(result["end"], 25.0)
        self.assertTrue(result["changed"])
        self.assertTrue(any("början" in item for item in result["adjustments"]))
        self.assertTrue(any("slutet" in item for item in result["adjustments"]))

    def test_preserves_reaction_if_trim_would_cut_it(self):
        transcript = [{"start": 0, "end": 4, "text": "setup"}]
        result = optimize_clip_boundaries(0, 20, transcript, [{"time": 18, "kind": "speech"}])
        self.assertLessEqual(result["start"], 18)
        self.assertGreaterEqual(result["end"], 18)

    def test_expands_boundary_to_preserve_a_cut_word(self):
        transcript = [{"start": 4.0, "end": 8.0, "text": "word crossing start"}]
        result = optimize_clip_boundaries(5.0, 25.0, transcript, [])
        self.assertAlmostEqual(result["start"], 4.0)
        self.assertIn("flyttade starten för att bevara tal", result["adjustments"])

    def test_keeps_minimum_duration(self):
        transcript = [{"start": 8, "end": 9, "text": "only speech"}]
        result = optimize_clip_boundaries(0, 20, transcript, [])
        self.assertGreaterEqual(result["duration"], 15)

    def test_leaves_boundaries_unchanged_without_transcript(self):
        result = optimize_clip_boundaries(5, 25, None, [])
        self.assertEqual(result["start"], 5)
        self.assertEqual(result["end"], 25)
        self.assertFalse(result["changed"])


if __name__ == "__main__":
    unittest.main()