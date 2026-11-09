import unittest

from app.main import payoff_timing_quality


class PayoffTimingQualityTests(unittest.TestCase):
    def test_rewards_speech_payoff_with_room_after_it(self):
        result = payoff_timing_quality(0, 20, [{"time": 16, "kind": "speech"}])
        self.assertEqual(result["score"], 4)
        self.assertEqual(result["anchor_kind"], "speech")
        self.assertEqual(result["position"], 0.8)

    def test_penalizes_payoff_too_close_to_end(self):
        result = payoff_timing_quality(0, 20, [{"time": 19.2, "kind": "speech"}])
        self.assertEqual(result["score"], -4)
        self.assertIn("för nära", result["reason"])

    def test_gives_smaller_bonus_for_earlier_payoff(self):
        result = payoff_timing_quality(0, 20, [{"time": 12, "kind": "audio"}])
        self.assertEqual(result["score"], 2)

    def test_prefers_speech_anchor_over_visual_anchor(self):
        result = payoff_timing_quality(0, 20, [
            {"time": 16, "kind": "visual"},
            {"time": 14, "kind": "speech"}
        ])
        self.assertEqual(result["anchor_kind"], "speech")

    def test_ignores_anchors_outside_clip(self):
        result = payoff_timing_quality(10, 20, [{"time": 9, "kind": "speech"}])
        self.assertIsNone(result["position"])
        self.assertEqual(result["score"], 0)


if __name__ == "__main__":
    unittest.main()
