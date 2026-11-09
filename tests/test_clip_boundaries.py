import unittest

from app.main import clip_boundary_quality


class ClipBoundaryQualityTests(unittest.TestCase):
    def test_detects_speech_cut_at_both_clip_edges(self):
        transcript = [{"start": 9.5, "end": 10.4, "text": "hello"},
                      {"start": 19.6, "end": 20.5, "text": "world"}]
        result = clip_boundary_quality(10.0, 20.0, transcript, [])
        self.assertTrue(result["speech_cut_at_start"])
        self.assertTrue(result["speech_cut_at_end"])
        self.assertEqual(result["score"], -14)

    def test_accepts_word_level_timestamps(self):
        transcript = [{"start": 9.0, "end": 11.0, "text": "hello",
                       "words": [{"start": 9.7, "end": 10.3, "text": "hello"}]}]
        result = clip_boundary_quality(10.0, 20.0, transcript, [])
        self.assertTrue(result["speech_cut_at_start"])

    def test_rewards_context_before_reaction_anchor(self):
        result = clip_boundary_quality(10.0, 30.0, [], [{"time": 13.0}])
        self.assertEqual(result["score"], 4)
        self.assertIn("upptakt före reaktionen", result["reasons"])

    def test_penalizes_reaction_starting_too_close_to_clip_start(self):
        result = clip_boundary_quality(10.0, 30.0, [], [{"time": 10.4}])
        self.assertEqual(result["score"], -5)


if __name__ == "__main__":
    unittest.main()