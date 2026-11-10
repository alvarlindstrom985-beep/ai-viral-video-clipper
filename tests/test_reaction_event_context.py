import unittest

from app.main import reaction_event_context


class ReactionEventContextTests(unittest.TestCase):
    def test_links_reaction_to_preceding_gameplay_event(self):
        transcript = [
            {"start": 10.0, "end": 11.0, "text": "police are coming"},
            {"start": 13.0, "end": 14.0, "text": "NO WAY hahaha"},
        ]
        result = reaction_event_context(transcript, 8, 20)
        self.assertTrue(result["linked"])
        self.assertEqual(result["score"], 5.0)
        self.assertEqual(result["gap_seconds"], 2.0)

    def test_does_not_link_distant_events(self):
        transcript = [
            {"start": 1.0, "end": 2.0, "text": "police are coming"},
            {"start": 15.0, "end": 16.0, "text": "NO WAY"},
        ]
        result = reaction_event_context(transcript, 0, 20)
        self.assertFalse(result["linked"])
        self.assertEqual(result["score"], 0.0)

    def test_reaction_without_gameplay_context_is_not_penalized(self):
        transcript = [{"start": 4.0, "end": 5.0, "text": "hahaha no way"}]
        result = reaction_event_context(transcript, 0, 10)
        self.assertFalse(result["linked"])
        self.assertEqual(result["score"], 0.0)

    def test_same_utterance_can_link_event_and_reaction(self):
        transcript = [{"start": 4.0, "end": 5.0, "text": "police! no way!"}]
        result = reaction_event_context(transcript, 0, 10)
        self.assertTrue(result["linked"])


if __name__ == "__main__":
    unittest.main()
