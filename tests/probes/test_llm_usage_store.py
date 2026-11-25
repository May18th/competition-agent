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
        """包装只记一次账，且调用的就是传进来的那个 invoke。

        2026-11-25 修：包装签名已改为 `_llm_invoke_with_quota(original_invoke, *args)`
        （`_wrap_llm` 按实例注入，否则评分实例会被换成正文实例的温度）。
        这里必须传真实 callable —— 旧写法传 `[]`，等于把 list 当函数调用，测的是错误现场。
        """
        import competition_agents
        from unittest.mock import MagicMock, patch

        response = SimpleNamespace(usage_metadata={"input_tokens": 5, "output_tokens": 3},
                                   response_metadata={})
        fake_invoke = MagicMock(return_value=response)
        with patch.object(competition_agents, "_backup_llm", None), \
             patch.object(competition_agents, "_quota_load", return_value={"calls": 0}), \
             patch.object(competition_agents, "_quota_save") as save_quota, \
             patch.object(competition_agents, "_record_llm_usage") as record_usage:
            result = competition_agents._llm_invoke_with_quota(fake_invoke, "prompt-x")

        self.assertIs(result, response)
        fake_invoke.assert_called_once_with("prompt-x")      # 参数原样透传，没被吃掉
        save_quota.assert_called_once()                      # 配额只 +1 一次
        record_usage.assert_called_once()
        self.assertIs(record_usage.call_args.args[0], response)
        self.assertIs(record_usage.call_args.args[2], fake_invoke)   # 记的是真正被调用的实例

    def test_quota_limit_blocks_call_without_recording(self):
        """达到上限必须当场拒绝，且不记账、不消耗模型——这是包装存在的意义。"""
        import competition_agents
        from unittest.mock import MagicMock, patch

        fake_invoke = MagicMock()
        with patch.object(competition_agents, "_quota_load",
                          return_value={"calls": competition_agents._QUOTA_DAILY_LIMIT}), \
             patch.object(competition_agents, "_quota_save") as save_quota, \
             patch.object(competition_agents, "_record_llm_usage") as record_usage:
            with self.assertRaises(RuntimeError):
                competition_agents._llm_invoke_with_quota(fake_invoke, "prompt-x")

        fake_invoke.assert_not_called()
        save_quota.assert_not_called()
        record_usage.assert_not_called()

    def test_stream_wrapper_records_cumulative_usage_once(self):
        import competition_agents
        from unittest.mock import patch

        self.assertTrue(competition_agents.llm.stream_usage)
        first_chunk = SimpleNamespace(content="正文", usage_metadata=None, response_metadata={})
        final_chunk = SimpleNamespace(
            content="", usage_metadata={"input_tokens": 30, "output_tokens": 9, "total_tokens": 39},
            response_metadata={},
        )

        def fake_stream(*args, **kwargs):
            return iter([first_chunk, final_chunk])

        with patch.object(competition_agents, "_record_llm_usage") as record_usage:
            chunks = list(competition_agents._llm_stream_with_usage(fake_stream, "prompt"))

        self.assertEqual(chunks, [first_chunk, final_chunk])
        record_usage.assert_called_once()
        self.assertIs(record_usage.call_args.args[0], final_chunk)   # 只认带 usage 的那个块
        self.assertGreaterEqual(record_usage.call_args.args[1], 0)
        self.assertIs(record_usage.call_args.args[2], fake_stream)


if __name__ == "__main__":
    unittest.main()
