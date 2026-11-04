import json
import tempfile
import unittest
from pathlib import Path

from scripts.performance_memory import build_record, load_history, save_record, summarize


class PerformanceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "filename": "clip_01.mp4",
            "hook_text": "THE FIGHT IS FAR FROM OVER",
            "hook_style": "mw4_cinematic",
            "content_type": "gaming",
            "framing_mode": "visual_full_frame_blurred_canvas",
        }

    def test_build_record_calculates_engagement_rate(self):
        record = build_record(self.metadata, {
            "views": 1000, "likes": 50, "comments": 5, "shares": 10,
            "saves": 5, "avg_watch_seconds": 8.5,
        }, "Instagram Reels")
        self.assertEqual(record["engagement_rate"], 0.07)
        self.assertEqual(record["platform"], "instagram reels")
        self.assertEqual(record["hook_style"], "mw4_cinematic")

    def test_rejects_negative_metrics(self):
        with self.assertRaises(ValueError):
            build_record(self.metadata, {"views": -1}, "tiktok")

    def test_save_and_summarize(self):
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "state" / "history.json"
            metadata_path = Path(directory) / "clip.json"
            metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")
            save_record(metadata_path, {"views": 500, "likes": 25}, "tiktok", history_path)
            save_record(metadata_path, {"views": 1500, "likes": 75}, "tiktok", history_path)
            history = load_history(history_path)
            rows = summarize(history)
            hook = next(row for row in rows if row["by"] == "hook_style")
            self.assertEqual(hook["posts"], 2)
            self.assertEqual(hook["average_views"], 1000.0)
            self.assertEqual(hook["average_engagement_rate"], 0.05)

    def test_missing_history_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_history(Path(directory) / "missing.json"), [])


if __name__ == "__main__":
    unittest.main()
