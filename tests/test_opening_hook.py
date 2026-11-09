import unittest

from app.main import score_opening_hook


class OpeningHookTests(unittest.TestCase):
    def test_early_reaction_phrase_gets_bonus(self):
        transcript = [
            {"start": 0.2, "end": 1.1, "text": "WHAT THE"},
            {"start": 1.2, "end": 2.4, "text": "NO WAY BRO"}
        ]
        result = score_opening_hook(0.0, [0.1, 0.1, 0.1], transcript)
        self.assertGreaterEqual(result["score"], 6.0)
        self.assertIn("reaktionsfras tidigt", result["signals"])

    def test_late_reaction_does_not_count_as_hook(self):
        transcript = [{"start": 8.0, "end": 9.0, "text": "WHAT THE"}]
        result = score_opening_hook(0.0, [0.02, 0.02, 0.02], transcript)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["signals"], [])

    def test_quiet_opening_is_not_penalized(self):
        result = score_opening_hook(0.0, [0.0, 0.0, 0.0], None)
        self.assertEqual(result["score"], 0.0)

    def test_early_laughter_and_speech_are_counted(self):
        transcript = [{"start": 0.1, "end": 2.5, "text": "Hahaha bro that was crazy"}]
        result = score_opening_hook(0.0, [0.02, 0.02, 0.02], transcript)
        self.assertGreater(result["score"], 0.0)
        self.assertIn("humor/skrattsignal tidigt", result["signals"])


if __name__ == "__main__":
    unittest.main()
