import unittest
from unittest.mock import patch

from app.main import normalize_csv_header, parse_csv_metric, candidate_similarity, is_near_duplicate, retention_signal_score, normalize_ai_review, learning_group_score, learned_category_bonus, performance_age_cohort, parse_publish_age_hours, build_performance_summary, performance_viewer_behavior


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



class PublicationAgeLearningTests(unittest.TestCase):
    def test_viewer_behavior_uses_per_1000_view_rates(self):
        result = performance_viewer_behavior([
            {"views": 1000, "engaged_views": 600, "likes": 50, "comments": 10, "shares": 5, "subscribers_gained": 2},
            {"views": 2000, "engaged_views": 1000, "likes": 100, "comments": 20, "shares": 10, "subscribers_gained": 4}
        ])
        self.assertEqual(result["engaged_views_pct"], 55.0)
        self.assertEqual(result["likes_per_1000_views"], 50.0)
        self.assertEqual(result["comments_per_1000_views"], 10.0)
        self.assertEqual(result["shares_per_1000_views"], 5.0)
        self.assertEqual(result["subscribers_gained_per_1000_views"], 2.0)

    def test_viewer_behavior_ignores_missing_metrics_and_zero_views(self):
        result = performance_viewer_behavior([
            {"views": 0, "likes": 99},
            {"views": 100, "likes": None, "shares": 2}
        ])
        self.assertIsNone(result["likes_per_1000_views"])
        self.assertEqual(result["likes_per_1000_views_samples"], 0)
        self.assertEqual(result["shares_per_1000_views"], 20.0)

    def test_age_cohorts_have_expected_boundaries(self):
        self.assertEqual(performance_age_cohort(24), "0–48 timmar")
        self.assertEqual(performance_age_cohort(72), "2–7 dagar")
        self.assertEqual(performance_age_cohort(400), "7–30 dagar")
        self.assertEqual(performance_age_cohort(1000), "30+ dagar")
        self.assertIsNone(performance_age_cohort(None))

    def test_publish_date_is_converted_to_age_hours(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        age = parse_publish_age_hours("2026-11-07T12:00:00Z", now=now)
        self.assertEqual(age, 48.0)

    def test_summary_compares_categories_within_age_cohorts(self):
        entries = []
        for category, score in (("Rage/ilska", 90), ("Humor/skratt", 40)):
            for index in range(3):
                entries.append({
                    "category": category, "variant": "v1", "format": "short",
                    "measurement_age_hours": 24, "performance_score": score,
                    "views": 100, "average_view_percentage": 80,
                    "stayed_to_watch_pct": 70
                })
        insights = build_performance_summary(entries)
        self.assertEqual(insights["videos_with_age_data"], 6)
        self.assertEqual(len(insights["age_cohorts"]), 1)
        self.assertEqual(len(insights["age_comparisons"]), 3)
        category_rows = [item for item in insights["age_comparisons"] if item["dimension"] == "category"]
        self.assertEqual(len(category_rows), 2)
        self.assertEqual(insights["age_comparisons"][0]["age_cohort"], "0–48 timmar")


class AdaptiveLearningTests(unittest.TestCase):
    def test_small_samples_are_shrunk_toward_channel_average(self):
        estimate = learning_group_score([
            {"performance_score": 100},
            {"performance_score": 100},
            {"performance_score": 100}
        ], 50, prior_strength=5)
        self.assertLess(estimate["adjusted_score"], 100)
        self.assertGreater(estimate["adjusted_score"], 50)
        self.assertEqual(estimate["confidence"], 0.375)

    def test_more_samples_increase_confidence(self):
        small = learning_group_score([{"performance_score": 80}] * 3, 50)
        large = learning_group_score([{"performance_score": 80}] * 20, 50)
        self.assertGreater(large["confidence"], small["confidence"])
        self.assertGreater(large["adjusted_score"], small["adjusted_score"])

    def test_category_bonus_is_zero_without_enough_channel_data(self):
        with patch("app.main.read_performance_entries", return_value=[
            {"format": "short", "views": 100, "performance_score": 80, "category": "Rage/ilska"}
        ]):
            self.assertEqual(learned_category_bonus(["Rage/ilska-signal"], "short"), 0.0)

    def test_category_bonus_is_bounded_and_uses_own_category_results(self):
        entries = [
            {"format": "short", "views": 100, "performance_score": 90, "category": "Rage/ilska"}
            for _ in range(4)
        ] + [
            {"format": "short", "views": 100, "performance_score": 40, "category": "Humor/skratt"}
            for _ in range(4)
        ]
        with patch("app.main.read_performance_entries", return_value=entries):
            bonus = learned_category_bonus(["Rage/ilska-signal"], "short")
        self.assertGreater(bonus, 0)
        self.assertLessEqual(abs(bonus), 3.0)

    def test_category_bonus_can_penalize_underperforming_categories(self):
        entries = [
            {"format": "short", "views": 100, "performance_score": 30, "category": "Rage/ilska"}
            for _ in range(4)
        ] + [
            {"format": "short", "views": 100, "performance_score": 80, "category": "Humor/skratt"}
            for _ in range(4)
        ]
        with patch("app.main.read_performance_entries", return_value=entries):
            bonus = learned_category_bonus(["Rage/ilska-signal"], "short")
        self.assertLess(bonus, 0)
        self.assertGreaterEqual(bonus, -3.0)

    def test_cached_entries_avoid_reloading_performance_file(self):
        entries = [
            {"format": "short", "views": 100, "performance_score": 90, "category": "Rage/ilska"}
            for _ in range(4)
        ] + [
            {"format": "short", "views": 100, "performance_score": 40, "category": "Humor/skratt"}
            for _ in range(4)
        ]
        with patch("app.main.read_performance_entries", side_effect=AssertionError("unexpected file read")):
            bonus = learned_category_bonus(["Rage/ilska-signal"], "short", entries)
        self.assertGreater(bonus, 0)


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


class AIReviewNormalizationTests(unittest.TestCase):
    def test_review_scores_are_clamped_and_lists_limited(self):
        result = normalize_ai_review({
            "score": 140, "hook_score": -5, "clarity_score": 72.6,
            "verdict": "Bra men kontrollera slutet",
            "strengths": ["Tydlig start", "Bra tempo", "Stark payoff", "Extra"],
            "weaknesses": ["Svag ljudnivå"]
        })
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["hook_score"], 0)
        self.assertEqual(result["clarity_score"], 73)
        self.assertEqual(len(result["strengths"]), 3)
        self.assertEqual(result["status"], "completed")

    def test_invalid_review_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_ai_review("not-json")


class RetentionSignalTests(unittest.TestCase):
    def test_strong_clip_structure_scores_higher(self):
        strong = retention_signal_score(10, 4, 5, 2, 1.0)
        weak = retention_signal_score(1, 1, 1, 0, 0.1)
        self.assertGreater(strong["score"], weak["score"])
        self.assertEqual(strong["label"], "Starka signaler")

    def test_score_is_bounded(self):
        result = retention_signal_score(100, 99, 99, 99, 99)
        self.assertEqual(result["score"], 100)

    def test_quiet_opening_is_not_claimed_as_failure(self):
        result = retention_signal_score(0, 3, 2, 2, 0.7)
        self.assertIn("öppningen kan behöva snabbare kontext eller en tydligare krok", result["reasons"])


class HookGeneratorTests(unittest.TestCase):
    def test_generates_three_distinct_transcript_grounded_hooks(self):
        from app.main import generate_hook_options
        transcript = [
            {"start": 10.0, "end": 11.0, "text": "Wait, what is happening?"},
            {"start": 14.0, "end": 15.0, "text": "That was insane!"},
            {"start": 20.0, "end": 21.0, "text": "No way!"}
        ]
        result = generate_hook_options(transcript, 10, 30)
        self.assertEqual(result["status"], "generated")
        self.assertEqual(len(result["options"]), 3)
        self.assertEqual(len({item["text"] for item in result["options"]}), 3)
        self.assertIn("Wait, what is happening", result["options"][0]["text"])

    def test_missing_transcript_creates_no_fabricated_hook(self):
        from app.main import generate_hook_options
        result = generate_hook_options([], 0, 20)
        self.assertEqual(result["status"], "no_transcript")
        self.assertEqual(result["options"], [])

class EditSuggestionTests(unittest.TestCase):
    def test_suggests_trim_for_long_silent_opening_and_ending(self):
        from app.main import suggest_edit_points
        transcript = [{"start": 3.0, "end": 8.0, "text": "Here we go"}, {"start": 25.0, "end": 27.0, "text": "That was wild"}]
        result = suggest_edit_points(0, 30, transcript, "short")
        self.assertEqual(result["status"], "suggested")
        self.assertAlmostEqual(result["recommended_start_seconds"], 2.75)
        self.assertAlmostEqual(result["recommended_end_seconds"], 27.45)
        self.assertGreater(result["suggested_trim_seconds"], 0)

    def test_no_transcript_keeps_original_timestamps(self):
        from app.main import suggest_edit_points
        result = suggest_edit_points(10, 40, [], "short")
        self.assertEqual(result["status"], "no_transcript")
        self.assertEqual(result["recommended_start_seconds"], 10)
        self.assertEqual(result["recommended_end_seconds"], 40)

    def test_short_clip_is_not_trimmed_below_safe_duration(self):
        from app.main import suggest_edit_points
        transcript = [{"start": 4.0, "end": 14.0, "text": "A long line"}]
        result = suggest_edit_points(0, 15, transcript, "short")
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["suggested_trim_seconds"], 0)

class RenderQualityTests(unittest.TestCase):
    def test_missing_render_is_rejected(self):
        from pathlib import Path
        from app.main import inspect_render_quality
        result = inspect_render_quality(Path('/missing-quality-test.mp4'), 30, 1080, 1920)
        self.assertFalse(result['passed'])


class HookOverlayRenderTests(unittest.TestCase):
    def test_hook_ass_contains_animated_text_and_correct_vertical_layout(self):
        from app.main import OUTPUTS, write_hook_overlay_ass
        path = write_hook_overlay_ass(
            "hookoverlaytest", "short", 1, "v1",
            {"text": "That was wild!"}, 30
        )
        try:
            content = path.read_text(encoding="utf-8")
            self.assertIn("PlayResX: 1080", content)
            self.assertIn("PlayResY: 1920", content)
            self.assertIn(r"\fad(180,220)", content)
            self.assertIn("That was wild!", content)
            self.assertIn("\n[Events]\n", content)
        finally:
            path.unlink(missing_ok=True)

    def test_hook_overlay_sanitizes_ass_control_characters(self):
        from app.main import write_hook_overlay_ass
        path = write_hook_overlay_ass(
            "hookoverlaysafe", "long", 1, "v2",
            {"text": r"Hello {\\pos(0,0)} world"}, 180
        )
        try:
            content = path.read_text(encoding="utf-8")
            self.assertIn("PlayResX: 1920", content)
            self.assertNotIn(r"{\\pos(0,0)}", content)
            self.assertIn("Hello", content)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
