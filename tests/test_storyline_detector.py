import unittest

from app.main import storyline_arc_quality


class StorylineArcQualityTests(unittest.TestCase):
    def test_finds_setup_event_and_aftermath(self):
        transcript = [
            {"start": 4, "end": 6, "text": "I am going to try this"},
            {"start": 10, "end": 12, "text": "No way!"},
            {"start": 14, "end": 16, "text": "That was incredible"},
        ]
        result = storyline_arc_quality(0, 20, transcript, [{"time": 11, "kind": "speech"}])
        self.assertTrue(result["has_setup"])
        self.assertTrue(result["has_event"])
        self.assertTrue(result["has_aftermath"])
        self.assertEqual(result["steps"], ["uppladdning", "händelse/reaktion", "efterspel"])
        self.assertEqual(result["score"], 9)

    def test_reports_missing_setup_and_aftermath(self):
        result = storyline_arc_quality(0, 20, [], [{"time": 11, "kind": "audio"}])
        self.assertFalse(result["has_setup"])
        self.assertFalse(result["has_aftermath"])
        self.assertEqual(result["score"], 1)

    def test_ignores_events_outside_clip(self):
        result = storyline_arc_quality(10, 20, [], [{"time": 9, "kind": "speech"}])
        self.assertIsNone(result["event_time"])
        self.assertEqual(result["score"], 0)

    def test_aftermath_can_be_a_following_reaction_anchor(self):
        result = storyline_arc_quality(0, 20, [], [
            {"time": 10, "kind": "speech"}, {"time": 12, "kind": "audio"}
        ])
        self.assertTrue(result["has_aftermath"])


if __name__ == "__main__":
    unittest.main()