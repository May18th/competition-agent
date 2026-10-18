import json
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module


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


if __name__ == "__main__":
    unittest.main()
