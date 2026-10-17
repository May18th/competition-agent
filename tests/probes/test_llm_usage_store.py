import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm_usage_store import aggregate_usage, record_usage


class TestLlmUsageStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "usage.sqlite")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_records_and_aggregates_without_exposing_raw_user_id(self):
        record_usage(self.db_path, user_id="user-secret-id", task_id="task-1",
                     stage="writing", section="市场分析", mode="deep", model="deepseek-chat",
                     prompt_tokens=100, completion_tokens=40, duration_ms=1200,
                     created_at="2026-10-17 10:00:00")
        record_usage(self.db_path, user_id="user-secret-id", stage="writing",
                     section="市场分析", prompt_tokens=20, completion_tokens=10,
                     created_at="2026-10-17 11:00:00")

        result = aggregate_usage(self.db_path, days=1, now=datetime(2026, 10, 17, 12))

        self.assertEqual(result["totals"]["calls"], 2)
        self.assertEqual(result["totals"]["total_tokens"], 170)
        self.assertEqual(result["daily"][0]["date"], "2026-10-17")
        self.assertEqual(result["sections"][0]["section"], "市场分析")
        self.assertEqual(result["users"][0]["calls"], 2)
        self.assertNotIn("user-secret-id", str(result))

    def test_invalid_days_are_bounded(self):
        result = aggregate_usage(self.db_path, days=999, now=datetime(2026, 10, 17))
        self.assertEqual(result["days"], 90)
        self.assertEqual(result["totals"]["calls"], 0)


if __name__ == "__main__":
    unittest.main()
