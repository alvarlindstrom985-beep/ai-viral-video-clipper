import unittest

from app.main import generate_edit_recommendations, build_performance_summary


class PerformanceEditingCoachTests(unittest.TestCase):
    def make_entries(self, counts=(3, 3, 3)):
        entries = []
        metrics = {
            "v1": (60, 70, 8, 2),
            "v2": (68, 78, 10, 4),
            "v3": (62, 72, 8.5, 2.5)
        }
        for variant, count in zip(("v1", "v2", "v3"), counts):
            stayed, retention, duration, shares = metrics[variant]
            for index in range(count):
                entries.append({
                    "format": "short",
                    "category": "Rage/ilska",
                    "variant": variant,
                    "measurement_age_hours": 24,
                    "views": 1000,
                    "stayed_to_watch_pct": stayed,
                    "average_view_percentage": retention,
                    "average_view_duration_sec": duration,
                    "shares": shares
                })
        return entries

    def test_generates_hook_retention_and_shareability_guidance(self):
        result = generate_edit_recommendations(self.make_entries())
        focuses = {item["focus"] for item in result}
        self.assertIn("Öppning och hook", focuses)
        self.assertIn("Retention och tempo", focuses)
        self.assertIn("Delningsvärde", focuses)
        hook = next(item for item in result if item["focus"] == "Öppning och hook")
        self.assertEqual(hook["recommended_variant"], "v2")
        self.assertEqual(hook["samples_per_variant"], {"v1": 3, "v2": 3, "v3": 3})

    def test_requires_three_valid_measurements_for_each_variant(self):
        result = generate_edit_recommendations(self.make_entries((3, 3, 2)))
        self.assertEqual(result, [])

    def test_does_not_mix_categories_or_publication_age_cohorts(self):
        entries = self.make_entries()
        other = self.make_entries()
        for item in other:
            item["category"] = "Humor/skratt"
            item["measurement_age_hours"] = 96
        result = generate_edit_recommendations(entries + other)
        self.assertEqual(len(result), 8)
        self.assertEqual({item["category"] for item in result}, {"Rage/ilska", "Humor/skratt"})
        self.assertEqual({item["age_cohort"] for item in result}, {"0–48 timmar", "2–7 dagar"})

    def test_learned_variant_hint_maps_clip_signals_to_youtube_categories(self):
        from app.main import learned_variant_hint
        entries = []
        for variant, score in (("v1", 60), ("v2", 85), ("v3", 70)):
            for _ in range(3):
                entries.append({
                    "format": "short", "category": "Rage/ilska", "variant": variant,
                    "measurement_age_hours": 24, "views": 1000,
                    "performance_score": score
                })
        hint = learned_variant_hint(["Rage/ilska-signal"], "short", entries)
        self.assertIsNotNone(hint)
        self.assertEqual(hint["recommended_variant"], "v2")
        self.assertEqual(hint["category"], "Rage/ilska")
        self.assertEqual(hint["samples_per_variant"], {"v1": 3, "v2": 3, "v3": 3})

    def test_learned_variant_hint_stays_empty_without_enough_data(self):
        from app.main import learned_variant_hint
        entries = [
            {"format": "short", "category": "Humor/skratt", "variant": "v1",
             "measurement_age_hours": 24, "views": 100, "performance_score": 90}
        ] * 3
        self.assertIsNone(learned_variant_hint(["Streamerhumor"], "short", entries))

    def test_summary_exposes_edit_recommendations(self):
        result = build_performance_summary(self.make_entries())
        self.assertTrue(result["edit_recommendations"])
        self.assertEqual(result["edit_recommendations"][0]["recommended_variant"], "v2")


if __name__ == "__main__":
    unittest.main()
