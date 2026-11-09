import unittest

from app.main import normalize_ai_review


class AIVisualReviewTests(unittest.TestCase):
    def test_visual_scores_are_clamped_and_warnings_are_limited(self):
        result = normalize_ai_review({
            "score": 91,
            "framing_score": 120,
            "composition_score": -5,
            "overlay_clutter_score": "72",
            "visual_warnings": [
                "Motivet ligger nära kanten",
                "Text täcker en viktig del",
                "Svag kontrast",
                "Rörig bakgrund",
                "Överlägg konkurrerar med motivet",
                "Extra varning som ska kapas"
            ]
        })
        self.assertEqual(result["framing_score"], 100)
        self.assertEqual(result["composition_score"], 0)
        self.assertEqual(result["overlay_clutter_score"], 72)
        self.assertEqual(len(result["visual_warnings"]), 5)
        self.assertNotIn("Extra varning som ska kapas", result["visual_warnings"])

    def test_missing_visual_fields_have_safe_defaults(self):
        result = normalize_ai_review({"score": 55})
        self.assertEqual(result["framing_score"], 0)
        self.assertEqual(result["composition_score"], 0)
        self.assertEqual(result["overlay_clutter_score"], 0)
        self.assertEqual(result["visual_warnings"], [])


if __name__ == "__main__":
    unittest.main()
