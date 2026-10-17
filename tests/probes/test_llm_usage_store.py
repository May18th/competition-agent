import os
import sys
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace

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

    def test_model_usage_hook_persists_request_metadata_only(self):
        import competition_agents
        from flask import Flask, g

        old_path = competition_agents._LLM_USAGE_DB_PATH
        competition_agents._LLM_USAGE_DB_PATH = self.db_path
        try:
            flask_app = Flask(__name__)
            result = SimpleNamespace(
                usage_metadata={"input_tokens": 40, "output_tokens": 12, "total_tokens": 52},
                response_metadata={},
            )
            model = SimpleNamespace(model="test-model")
            target = SimpleNamespace(__self__=model)
            with flask_app.test_request_context(
                    "/api/revise_chapter", json={"history_id": 23, "chapter": "市场分析", "mode": "deep"}):
                g.uid = "uid-private"
                competition_agents._record_llm_usage(result, 321, target)

            aggregated = aggregate_usage(self.db_path, days=1)
            self.assertEqual(aggregated["totals"]["total_tokens"], 52)
            self.assertEqual(aggregated["sections"][0]["section"], "市场分析")
            self.assertEqual(aggregated["models"][0]["model"], "test-model")
            self.assertNotIn("uid-private", str(aggregated))
        finally:
            competition_agents._LLM_USAGE_DB_PATH = old_path

    def test_quota_wrapped_invoke_records_usage_once(self):
        import competition_agents
        from unittest.mock import patch

        response = SimpleNamespace(usage_metadata={"input_tokens": 5, "output_tokens": 3},
                                   response_metadata={})
        with patch.object(competition_agents, "_llm_invoke_original", return_value=response), \
             patch.object(competition_agents, "_backup_llm", None), \
             patch.object(competition_agents, "_quota_load", return_value={"calls": 0}), \
             patch.object(competition_agents, "_quota_save") as save_quota, \
             patch.object(competition_agents, "_record_llm_usage") as record_usage:
            result = competition_agents._llm_invoke_with_quota([])

        self.assertIs(result, response)
        save_quota.assert_called_once()
        record_usage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
