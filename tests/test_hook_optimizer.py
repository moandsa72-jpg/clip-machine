import unittest

from scripts.optimize_moments import optimize, score_hook, select_short_hook


class HookOptimizerTests(unittest.TestCase):
    def test_hook_score_penalizes_weak_opening(self):
        weak = score_hook("Okay, so this is the secret")
        strong = score_hook("The truth is finally revealed to you")
        self.assertGreater(strong, weak)

    def test_short_hook_is_at_most_five_words(self):
        hook = select_short_hook("This is the unbelievable truth about the final mission")
        self.assertLessEqual(len(hook.split()), 5)

    def test_visual_only_campaign_gets_curated_hook(self):
        moment = {"start": 40, "end": 64, "visual_only": True, "score": 8}
        result = optimize(moment, [], [], 3.0, "call_of_duty_mw4_s1")
        self.assertEqual(result["hook_text"], "THE FIGHT IS FAR FROM OVER")
        self.assertEqual(result["hook_style"], "mw4_cinematic")
        self.assertIn("not dialogue", result["hook_source_text"])


if __name__ == "__main__":
    unittest.main()
