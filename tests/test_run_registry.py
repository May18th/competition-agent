# -*- coding: utf-8 -*-
"""生成运行清单的单元测试（零消费，不调任何外部模型）。

运行方式：
    python -m unittest tests.test_run_registry -v
"""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import backend.competition_agents as ca
import backend.llm_usage_store as store
import backend.run_registry as rr


class TestFingerprints(unittest.TestCase):
    def test_code_version_stable_and_nonempty(self):
        v1 = rr.code_version()
        v2 = rr.code_version()
        self.assertEqual(v1, v2)
        self.assertGreaterEqual(len(v1), 8)

    def test_kb_snapshot_nonempty(self):
        self.assertTrue(rr.kb_snapshot(), "知识库指纹不该为空")

    def test_code_version_changes_with_content(self):
        """改一行 prompt 指纹就得变，否则清单追溯不到版本。"""
        real = rr.code_version()
        with mock.patch.object(rr, "_CODE_FILES", ("requirements.txt",)):
            rr._fingerprint_cache.pop("code", None)
            other = rr.code_version()
            rr._fingerprint_cache.pop("code", None)
        self.assertNotEqual(real, other)
        self.assertEqual(rr.code_version(), real)   # 恢复


class TestRecordRun(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        fd, self.usage = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store.record_usage(self.usage, task_id="T1", user_id="u1", mode="fast",
                           stage="writing", prompt_tokens=100, completion_tokens=50)
        store.record_usage(self.usage, task_id="T1", user_id="u1", mode="fast",
                           stage="judging", prompt_tokens=30, completion_tokens=20)

    def tearDown(self):
        for p in (self.db, self.usage):
            for _ in range(3):
                try:
                    os.remove(p)
                    break
                except (PermissionError, FileNotFoundError):
                    pass

    def test_one_row_per_run_with_token_rollup(self):
        rr.record_run(self.db, self.usage, task_id="T1", mode="fast",
                      competition="互联网+", idea="某创意", user_id="u1",
                      duration_ms=1234, quality_score=92, quality_reasons=["缺图表"],
                      quality_missing=[], history_id=7)
        rows = rr.recent_runs(self.db)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["task_id"], "T1")
        self.assertEqual(r["calls"], 2)
        self.assertEqual(r["total_tokens"], 200)
        self.assertEqual(r["quality_score"], 92)
        self.assertEqual(json.loads(r["quality_reasons"]), ["缺图表"])
        self.assertEqual(r["history_id"], 7)
        self.assertEqual(r["export_state"], "pending")
        self.assertEqual(r["code_version"], rr.code_version())

    def test_idea_not_stored_in_plain(self):
        """只存创意摘要指纹，不存原文。"""
        rr.record_run(self.db, self.usage, task_id="T2", idea="这是我的完整创意原文不许落库")
        row = rr.recent_runs(self.db)[0]
        self.assertNotIn("完整创意原文", json.dumps(row, ensure_ascii=False))

    def test_update_export_by_history(self):
        rr.record_run(self.db, self.usage, task_id="T1", history_id=7)
        rr.update_export(self.db, history_id=7, state="warned", warnings=["套话：闭环"])
        row = rr.recent_runs(self.db)[0]
        self.assertEqual(row["export_state"], "warned")
        self.assertEqual(json.loads(row["export_warnings"]), ["套话：闭环"])

    def test_update_export_by_task(self):
        rr.record_run(self.db, self.usage, task_id="T1")
        rr.update_export(self.db, task_id="T1", state="ok")
        self.assertEqual(rr.recent_runs(self.db)[0]["export_state"], "ok")

    def test_idempotent_rebuild(self):
        rr.record_run(self.db, self.usage, task_id="T1", history_id=7)
        rr.record_run(self.db, self.usage, task_id="T1", history_id=7)
        self.assertEqual(len(rr.recent_runs(self.db)), 1)


if __name__ == "__main__":
    unittest.main()
