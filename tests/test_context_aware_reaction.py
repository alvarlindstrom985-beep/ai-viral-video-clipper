import unittest

from app.main import context_aware_reaction_score


class ContextAwareReactionPriorityTests(unittest.TestCase):
    def test_clear_streamer_reaction_gets_priority_bonus(self):
        result = context_aware_reaction_score(
            ["haha"], ["NO WAY"], 2, [], 0, ["mission complete"]
        )
        self.assertTrue(result["has_clear_reaction"])
        self.assertEqual(result["reaction_focus_adjustment"], 8.0)
        self.assertGreater(result["priority_score"], result["gameplay_context_score"])

    def test_gameplay_without_streamer_reaction_gets_penalty(self):
        result = context_aware_reaction_score(
            [], [], 0, [], 0, ["mission complete", "police chase"]
        )
        self.assertFalse(result["has_clear_reaction"])
        self.assertEqual(result["gameplay_context_score"], 3.0)
        self.assertEqual(result["reaction_focus_adjustment"], -12.0)

    def test_neutral_clip_without_reaction_or_gameplay_is_not_penalized(self):
        result = context_aware_reaction_score([], [], 0, [], 0, [])
        self.assertEqual(result["reaction_focus_adjustment"], 0.0)

    def test_visual_reaction_can_trigger_priority(self):
        result = context_aware_reaction_score([], [], 0, [], 10, [])
        self.assertTrue(result["has_clear_reaction"])
        self.assertEqual(result["reaction_focus_adjustment"], 8.0)


if __name__ == "__main__":
    unittest.main()
