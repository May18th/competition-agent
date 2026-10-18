import json
import os
import sqlite3
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module
from llm_usage_store import aggregate_usage, record_usage


class AdminOperationsTests(unittest.TestCase):
    def test_admin_scope_has_bounded_date_window_and_test_filter(self):
        scope = app_module.admin_scope({"days": "7", "start": "2026-10-01", "end": "2026-10-07"})
        self.assertEqual(scope["start"], "2026-10-01 00:00:00")
        self.assertEqual(scope["end"], "2026-10-07 23:59:59")
        self.assertEqual(scope["days"], 7)
        where, params = app_module.admin_history_where(scope)
        self.assertIn("created_time >= ?", where)
        self.assertIn("created_time <= ?", where)
        self.assertIn("测试赛事", where)
        self.assertEqual(params[-2:], (scope["start"], scope["end"]))

    def test_admin_scope_rejects_invalid_and_unbounded_dates(self):
        with self.assertRaises(ValueError):
            app_module.admin_scope({"days": "0"})
        with self.assertRaises(ValueError):
            app_module.admin_scope({"start": "not-a-date"})
        with self.assertRaises(ValueError):
            app_module.admin_scope({"days": "999"})

    def test_competition_display_merges_aliases_and_hides_unknown(self):
        profiles = [
            {"name": "挑战杯", "aliases": ["挑战杯中国大学生创业计划竞赛", " 挑战杯 "]},
            {"name": "国创赛", "aliases": ["国家级大学生创新创业训练计划竞赛"]},
        ]
        self.assertEqual(
            app_module.admin_competition_display("挑战杯中国大学生创业计划竞赛", profiles),
            "挑战杯",
        )
        self.assertEqual(app_module.admin_competition_display(" 国创赛 ", profiles), "国创赛")
        self.assertIsNone(app_module.admin_competition_display("正大杯", profiles))
        self.assertIsNone(app_module.admin_competition_display("", profiles))

    def test_competition_display_accepts_profile_dict_aliases_casefolded(self):
        profiles = [{"name": "ICAN", "aliases": ["ican 国际创新创业大赛"]}]
        self.assertEqual(
            app_module.admin_competition_display(" ICAN 国际创新创业大赛 ", profiles),
            "ICAN",
        )

    def test_admin_stat_endpoints_reject_unbounded_ranges_consistently(self):
        old_token = app_module.ADMIN_TOKEN
        app_module.ADMIN_TOKEN = "probe-token"
        client = app_module.app.test_client()
        try:
            for path in ("/api/admin/stats?days=999", "/api/admin/quota?days=999"):
                response = client.get(path, headers={"X-Admin-Token": "probe-token"})
                self.assertEqual(response.status_code, 400, path)
                self.assertFalse(response.get_json()["success"], path)
        finally:
            app_module.ADMIN_TOKEN = old_token

    def test_quality_summary_separates_deliverable_warning_block_and_recovery(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE history (
                id INTEGER PRIMARY KEY, competition_name TEXT, result_data TEXT,
                created_time TEXT, status TEXT
            );
            CREATE TABLE export_reviews (
                id INTEGER PRIMARY KEY, history_id INTEGER, score INTEGER,
                reasons TEXT, passed INTEGER, created_time TEXT
            );
            CREATE TABLE gen_failures (
                id INTEGER PRIMARY KEY, type TEXT, status TEXT,
                competition_name TEXT, created_time TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO history VALUES (?, ?, ?, ?, ?)",
            [
                (1, "挑战杯", "{}", "2026-10-03 10:00:00", "success"),
                (2, "未知比赛", "{}", "2026-10-04 10:00:00", "success"),
            ],
        )
        conn.executemany(
            "INSERT INTO export_reviews VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, 92, "[]", 1, "2026-10-03 10:05:00"),
                (2, 1, 82, '["缺少目录"]', 1, "2026-10-03 10:06:00"),
                (3, 2, 0, '["正文为空"]', 0, "2026-10-04 10:06:00"),
            ],
        )
        conn.execute(
            "INSERT INTO gen_failures VALUES (1, 'generate', 'auto-recovered', '挑战杯', '2026-10-03 10:07:00')"
        )
        conn.commit()
        profiles = [{"name": "挑战杯", "aliases": []}]
        scope = {"start": "2026-10-01 00:00:00", "end": "2026-10-07 23:59:59", "days": 7}
        summary = app_module.admin_quality_summary(conn, scope, profiles)
        self.assertEqual(summary["metrics"]["deliverable_success"], 1)
        self.assertEqual(summary["metrics"]["soft_warning"], 1)
        self.assertEqual(summary["metrics"]["hard_blocked"], 1)
        self.assertEqual(summary["metrics"]["recovery_success"], 1)
        self.assertEqual(summary["competitions"], [{"name": "挑战杯", "count": 1}])
        conn.close()

    def test_usage_dashboard_has_bounded_aggregates_and_anonymized_dimensions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "usage.sqlite")
            record_usage(db_path, task_id="task-a", user_id="alice", stage="generate",
                         section="项目概述", model="deepseek-flash", total_tokens=120,
                         created_at="2026-10-17 10:00:00")
            record_usage(db_path, task_id="task-b", user_id="alice", stage="proofread",
                         section="风险分析", model="deepseek-flash", total_tokens=80,
                         created_at="2026-10-17 11:00:00")
            result = aggregate_usage(db_path, days=999, limit=200,
                                     now=datetime(2026, 10, 18, 12, 0, 0))
            self.assertEqual(result["days"], 90)
            self.assertEqual(result["totals"]["total_tokens"], 200)
            self.assertEqual(result["totals"]["avg_tokens_per_call"], 100)
            self.assertEqual(result["forecast"]["seven_day_tokens"], 200 * 7 / 90)
            self.assertEqual(result["tasks"][0]["task_id"], "task-a")
            self.assertEqual(len(result["users"][0]["user_key"]), 16)
            self.assertEqual(result["models"][0]["model"], "deepseek-flash")

    def test_usage_dashboard_empty_database_is_safe(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tempdir:
            result = aggregate_usage(os.path.join(tempdir, "empty.sqlite"), days=0)
            self.assertEqual(result["totals"]["calls"], 0)
            self.assertEqual(result["tasks"], [])
            self.assertEqual(result["forecast"]["seven_day_tokens"], 0)

    def test_operational_alerts_have_stable_levels_and_dedupe_keys(self):
        alerts = app_module.admin_alerts({
            "quota": {"calls": 98, "limit": 100, "date": "2026-10-18"},
            "failure_rate": 0.32,
            "overdue_tickets": 2,
            "avg_latency_sec": 141,
            "updated_at": "2026-10-18T12:00:00+08:00",
        })
        self.assertEqual({item["key"] for item in alerts}, {
            "quota:2026-10-18", "failure-rate", "tickets:overdue", "latency:avg"
        })
        self.assertTrue(all(item["level"] in {"info", "warning", "critical"} for item in alerts))
        self.assertTrue(all(item["updated_at"] == "2026-10-18T12:00:00+08:00" for item in alerts))
        self.assertEqual(app_module.admin_alerts({"failure_rate": 0})[0:1], [])

    def test_service_diagnose_is_direct_and_returns_safe_check_structure(self):
        result = app_module.admin_service_diagnose()
        self.assertIn(result["status"], {"ok", "warning", "error"})
        self.assertIsInstance(result["checks"], list)
        self.assertTrue(all({"key", "status", "detail"} <= set(item) for item in result["checks"]))

    def test_alert_and_diagnose_routes_have_safe_error_boundary(self):
        old_token = app_module.ADMIN_TOKEN
        app_module.ADMIN_TOKEN = "probe-token"
        client = app_module.app.test_client()
        try:
            response = client.get("/api/admin/diagnose", headers={"X-Admin-Token": "probe-token"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("checks", response.get_json())
            response = client.get("/api/admin/alert_status?days=999",
                                  headers={"X-Admin-Token": "probe-token"})
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.get_json()["success"])
        finally:
            app_module.ADMIN_TOKEN = old_token

    def test_issue_update_records_status_transition_and_sla_metadata(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE issues (
                id INTEGER PRIMARY KEY, kind TEXT, source TEXT, content TEXT,
                created_time TEXT, status TEXT, resolved_time TEXT, resolution TEXT,
                priority TEXT, assignee TEXT, due_time TEXT, updated_time TEXT,
                updated_by TEXT
            );
            CREATE TABLE issue_audit (
                id INTEGER PRIMARY KEY, issue_id INTEGER, actor TEXT, action TEXT,
                old_status TEXT, new_status TEXT, created_time TEXT, detail TEXT
            );
            INSERT INTO issues VALUES
                (1, 'backend', 'probe', '导出慢', '2026-10-01 10:00', 'open', '', '',
                 'normal', '', '2026-10-20 10:00', '', '');
            """
        )
        result = app_module.admin_update_issue(
            conn, 1, {"status": "processing", "priority": "high", "assignee": "ops",
                      "due_time": "2026-10-19 18:00", "resolution": "已安排排查"}, "admin-a"
        )
        self.assertEqual(result["status"], "processing")
        row = conn.execute("SELECT * FROM issues WHERE id=1").fetchone()
        self.assertEqual(row["priority"], "high")
        self.assertEqual(row["assignee"], "ops")
        audit = conn.execute("SELECT actor, old_status, new_status, detail FROM issue_audit").fetchone()
        self.assertEqual(tuple(audit), ("admin-a", "open", "processing", "已安排排查"))
        conn.close()

    def test_issue_list_reports_overdue_without_exposing_unknown_fields(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE issues (
                id INTEGER PRIMARY KEY, kind TEXT, source TEXT, content TEXT,
                created_time TEXT, status TEXT, resolved_time TEXT, resolution TEXT,
                priority TEXT, assignee TEXT, due_time TEXT, updated_time TEXT,
                updated_by TEXT
            );
            INSERT INTO issues VALUES
                (1, 'frontend', 'probe', '移动端问题', '2026-10-01 10:00', 'open', '', '',
                 'high', 'ops', '2026-10-02 10:00', '', '');
            """
        )
        rows = app_module.admin_list_issues(conn, {"status": "open"}, now="2026-10-03 12:00:00")
        self.assertEqual(rows["overdue"], 1)
        self.assertEqual(rows["items"][0]["assignee"], "ops")
        self.assertNotIn("content_raw", rows["items"][0])
        conn.close()


if __name__ == "__main__":
    unittest.main()
