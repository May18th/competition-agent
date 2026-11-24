# -*- coding: utf-8 -*-
"""LLM 用量归属的单元测试（零消费，不调任何外部模型）

覆盖两件事：
1. 后台生成线程能把 task_id / user_id / mode / stage 传进用量记录
   （历史上这几列恒为空，导致单次生成成本只能靠假设）；
2. 按单次生成的聚合口径（调用次数、token 分布、按版本分桶）算得对。

运行方式：
    python -m unittest tests.test_usage_tracking -v
"""
import hashlib
import os
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

import backend.competition_agents as ca
import backend.llm_usage_store as store
import backend.stage_reporter as sr


class _FakeResult:
    """冒充 LangChain 返回对象，只带 usage 元数据。"""

    def __init__(self, prompt=100, completion=50):
        self.usage_metadata = {
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": prompt + completion,
        }
        self.response_metadata = {}


class TestTaskContext(unittest.TestCase):
    """线程本地任务上下文：生成线程写、Agent 节点读。"""

    def tearDown(self):
        sr.clear_current_task()

    def test_context_roundtrip(self):
        sr.set_current_task("t-001", "u-abc", "deep")
        sr.report_stage("writing")
        self.assertEqual(sr.current_task_id(), "t-001")
        self.assertEqual(sr.current_user_id(), "u-abc")
        self.assertEqual(sr.current_mode(), "deep")
        self.assertEqual(sr.current_stage(), "writing")

    def test_clear_resets_everything(self):
        sr.set_current_task("t-002", "u-abc", "fast")
        sr.report_stage("defense")
        sr.clear_current_task()
        self.assertIsNone(sr.current_task_id())
        self.assertIsNone(sr.current_user_id())
        self.assertIsNone(sr.current_mode())
        self.assertIsNone(sr.current_stage())

    def test_context_is_thread_local(self):
        """并发生成时任务上下文不能串台（16 路并发的前提）。"""
        seen = {}

        def worker():
            sr.set_current_task("t-worker", "u-worker", "fast")
            sr.report_stage("ppt")
            seen["task"] = sr.current_task_id()
            seen["stage"] = sr.current_stage()

        sr.set_current_task("t-main", "u-main", "deep")
        th = threading.Thread(target=worker)
        th.start()
        th.join()
        self.assertEqual(seen["task"], "t-worker")
        self.assertEqual(seen["stage"], "ppt")
        self.assertEqual(sr.current_task_id(), "t-main")


class TestUsagePersistence(unittest.TestCase):
    """后台线程无请求上下文时，用量记录仍能归到 task 与用户。"""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.patcher = mock.patch.object(ca, "_LLM_USAGE_DB_PATH", self.db_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        sr.clear_current_task()
        for _ in range(3):
            try:
                os.remove(self.db_path)
                break
            except (PermissionError, FileNotFoundError):
                pass

    def _rows(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM llm_usage")]

    def test_record_carries_task_and_user_from_worker_thread(self):
        def worker():
            sr.set_current_task("task-abc", "uid-123", "deep")
            sr.report_stage("writing")
            ca._record_llm_usage(_FakeResult(), 1200, None)

        th = threading.Thread(target=worker)
        th.start()
        th.join()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["task_id"], "task-abc")
        self.assertEqual(row["mode"], "deep")
        self.assertEqual(row["stage"], "writing")
        self.assertEqual(row["user_key"], hashlib.sha256(b"uid-123").hexdigest()[:16])
        self.assertEqual(row["prompt_tokens"], 100)
        self.assertEqual(row["completion_tokens"], 50)
        self.assertEqual(row["total_tokens"], 150)

    def test_task_id_empty_when_no_context(self):
        """没有任务上下文时（比如请求外调用）不编造 task_id。"""
        ca._record_llm_usage(_FakeResult(), 10, None)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["task_id"], "")
        self.assertEqual(rows[0]["user_key"], "anonymous")


class TestPerGenerationSummary(unittest.TestCase):
    """按单次生成聚合的口径。"""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store.record_usage(self.db_path, task_id="T1", user_id="u1", mode="deep",
                           stage="writing", prompt_tokens=1000, completion_tokens=500,
                           duration_ms=3000)
        store.record_usage(self.db_path, task_id="T1", user_id="u1", mode="deep",
                           stage="judging", prompt_tokens=500, completion_tokens=200,
                           duration_ms=1000)
        store.record_usage(self.db_path, task_id="T2", user_id="u2", mode="fast",
                           stage="writing", prompt_tokens=300, completion_tokens=100,
                           duration_ms=800)
        # 无 task_id 的历史行不该污染单次成本口径
        store.record_usage(self.db_path, task_id="", user_id="u3", mode="fast",
                           prompt_tokens=9999, completion_tokens=9999)

    def tearDown(self):
        for _ in range(3):
            try:
                os.remove(self.db_path)
                break
            except (PermissionError, FileNotFoundError):
                pass

    def test_summary_counts_only_task_rows(self):
        summary = store.per_generation_summary(self.db_path, days=30)
        self.assertEqual(summary["task_count"], 2)
        # T1 两次调用、T2 一次 → 均值 1.5
        self.assertEqual(summary["calls"]["mean"], 1.5)
        self.assertEqual(summary["calls"]["total"], 3)
        # T1 = 1500+700, T2 = 400 → 均值 1300
        self.assertEqual(summary["total_tokens"]["mean"], 1300)
        self.assertEqual(summary["total_tokens"]["min"], 400)
        self.assertEqual(summary["total_tokens"]["max"], 2200)

    def test_by_mode_buckets(self):
        summary = store.per_generation_summary(self.db_path, days=30)
        deep = summary["by_mode"]["deep"]
        fast = summary["by_mode"]["fast"]
        self.assertEqual(deep["task_count"], 1)
        self.assertEqual(deep["avg_calls"], 2.0)
        self.assertEqual(deep["avg_tokens"], 2200)
        self.assertEqual(fast["task_count"], 1)
        self.assertEqual(fast["avg_calls"], 1.0)
        self.assertEqual(fast["avg_tokens"], 400)

    def test_aggregate_tasks_lists_stages(self):
        tasks = store.aggregate_tasks(self.db_path, days=30)
        self.assertEqual(len(tasks), 2)
        t1 = next(t for t in tasks if t["task_id"] == "T1")
        self.assertEqual(t1["calls"], 2)
        self.assertEqual(t1["total_tokens"], 2200)
        stages = set((t1["stages"] or "").split(","))
        self.assertEqual(stages, {"writing", "judging"})

    def test_empty_db_returns_zero_shape(self):
        fd, empty_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            summary = store.per_generation_summary(empty_db, days=30)
            self.assertEqual(summary["task_count"], 0)
            self.assertEqual(summary["by_mode"], {})
        finally:
            os.remove(empty_db)


if __name__ == "__main__":
    unittest.main()
