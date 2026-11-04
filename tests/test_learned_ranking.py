import unittest

from scripts.performance_memory import learned_adjustment


class LearnedRankingTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "campaign_id": "mw4",
            "hook_style": "mw4_cinematic",
            "content_type": "gaming",
            "framing_mode": "full_frame",
        }

    def test_no_history_has_zero_adjustment(self):
        result = learned_adjustment(self.metadata, [])
        self.assertEqual(result["adjustment"], 0.0)

    def test_small_sample_does_not_change_rank(self):
        history = [
            {"campaign_id": "mw4", "hook_style": "mw4_cinematic",
             "content_type": "gaming", "framing_mode": "full_frame",
             "platform": "instagram", "engagement_rate": 0.2,
             "avg_watch_seconds": 12}
        ]
        result = learned_adjustment(self.metadata, history)
        self.assertEqual(result["adjustment"], 0.0)
        self.assertEqual(result["samples"], 1)

    def test_repeated_better_results_create_capped_positive_adjustment(self):
        history = []
        for _ in range(4):
            history.append({
                "campaign_id": "mw4", "hook_style": "mw4_cinematic",
                "content_type": "gaming", "framing_mode": "full_frame",
                "platform": "instagram", "engagement_rate": 0.2,
                "avg_watch_seconds": 12,
            })
        for _ in range(4):
            history.append({
                "campaign_id": "mw4", "hook_style": "statement",
                "content_type": "gaming", "framing_mode": "full_frame",
                "platform": "instagram", "engagement_rate": 0.01,
                "avg_watch_seconds": 2,
            })
        result = learned_adjustment(self.metadata, history)
        self.assertGreater(result["adjustment"], 0)
        self.assertLessEqual(result["adjustment"], 4.0)

    def test_platforms_are_not_mixed_when_filter_is_given(self):
        history = []
        for _ in range(4):
            history.append({
                "campaign_id": "mw4", "hook_style": "mw4_cinematic",
                "content_type": "gaming", "framing_mode": "full_frame",
                "platform": "tiktok", "engagement_rate": 0.2,
                "avg_watch_seconds": 12,
            })
        result = learned_adjustment(self.metadata, history, platform="instagram")
        self.assertEqual(result["adjustment"], 0.0)
        self.assertEqual(result["samples"], 0)


if __name__ == "__main__":
    unittest.main()
