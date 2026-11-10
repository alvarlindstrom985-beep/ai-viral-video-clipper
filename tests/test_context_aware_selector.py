import unittest

from app.main import context_aware_reaction_score


class ContextAwareReactionScoreTests(unittest.TestCase):
    def test_strong_streamer_reaction_outweighs_gameplay_keywords(self):
        reaction = context_aware_reaction_score(
            ["hahaha"], ["WHAT"], 3, ["what the hell"], 12, ["explosion", "police"]
        )
        gameplay_only = context_aware_reaction_score([], [], 0, [], 0, ["explosion", "police", "chase"])
        self.assertGreater(reaction["priority_score"], gameplay_only["gameplay_context_score"])
        self.assertTrue(reaction["has_clear_reaction"])
        self.assertFalse(gameplay_only["has_clear_reaction"])

    def test_gameplay_context_is_capped(self):
        few = context_aware_reaction_score([], [], 0, [], 0, ["crash"])
        many = context_aware_reaction_score([], [], 0, [], 0, ["crash", "police", "heist", "explosion", "chase"])
        self.assertEqual(many["gameplay_context_score"], 4.5)
        self.assertLessEqual(many["gameplay_context_score"] - few["gameplay_context_score"], 3.0)

    def test_reaction_score_is_bounded(self):
        result = context_aware_reaction_score(["haha"] * 10, ["WHAT"] * 10, 20, ["rage"] * 10, 100, [])
        self.assertLessEqual(result["priority_score"], 30.0)

    def test_visual_reaction_can_count_without_transcript_phrase(self):
        result = context_aware_reaction_score([], [], 0, [], 12, [])
        self.assertTrue(result["has_clear_reaction"])
        self.assertGreater(result["priority_score"], 0)


if __name__ == "__main__":
    unittest.main()
