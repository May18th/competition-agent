# -*- coding: utf-8 -*-
"""导出闸门口径一致性探针（2026-11-25）。

背景：内容评分门原先只挂在 export_word 上，export_pdf / export_pptx / export_zip
能绕过同一个判据——同一份稿子 Word 被拦、压缩包却能下。本探针锁住三件事：

1. 四个主交付物路由都调用了统一入口 `_export_gate_guard`；
2. 评分不达标时返回 422，且响应里带 code=quality_fail 与 score；
3. 拿不到历史记录（只传纯文本）时放行，不误伤外部调用。
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module


class ExportGateUniformityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db = app_module.DB_PATH
        app_module.DB_PATH = os.path.join(self.tempdir.name, "gate.db")
        # 用应用自己的建表逻辑：导出链路会读 mode/history 等多列，手写残缺 schema 会假失败
        app_module.init_db()
        self.client = app_module.app.test_client()
        # 导出路由要求登录态：先访问首页拿到服务端下发的 comp_uid cookie
        self.client.get("/")

    def tearDown(self):
        app_module.DB_PATH = self.old_db
        self.tempdir.cleanup()

    def _insert(self, rid, payload):
        conn = app_module.get_db()
        try:
            conn.execute(
                "INSERT INTO history (id, result_data, user_id) VALUES (?, ?, ?)",
                (rid, json.dumps(payload, ensure_ascii=False), "u-gate"),
            )
            conn.commit()
        finally:
            conn.close()

    # ---------- 1. 源码层：四个路由都挂了同一道门 ----------
    def test_all_four_export_routes_use_shared_gate(self):
        src = io.open(os.path.join(ROOT, "backend", "app.py"), encoding="utf-8").read()
        self.assertEqual(
            1, len(re.findall(r"^def _export_gate_guard\(", src, re.M)),
            "统一闸门入口应只有一个定义",
        )
        for fn in ("export_word", "export_pdf", "export_pptx", "export_zip"):
            m = re.search(r"^def %s\(\):" % fn, src, re.M)
            self.assertIsNotNone(m, "找不到路由函数 %s" % fn)
            start = m.end()
            nxt = re.search(r"^def \w+\(", src[start:], re.M)
            body = src[start: start + (nxt.start() if nxt else 4000)]
            self.assertIn(
                "_export_gate_guard(data)", body,
                "%s 没有走统一导出闸门，会出现「Word 被拦、其它格式能下」的绕行" % fn,
            )

    # ---------- 2. 坏稿子：四个路由都应 422 ----------
    def test_low_score_record_is_blocked_on_all_formats(self):
        # 空正文 + 占位符，必然触发 quality_gate 的一票否决
        self._insert(1, {"proposal": "", "competitor": "", "judge": "",
                         "mode": "fast", "competition": "iCAN大赛"})
        # 回源只允许取本人记录，这里固定 uid 与插入记录一致
        with patch.object(app_module, "_current_uid", return_value="u-gate"):
            for path in ("/api/export_word", "/api/export_pdf",
                         "/api/export_pptx", "/api/export_zip"):
                resp = self.client.post(path, json={"history_id": 1, "mode": "fast"})
                self.assertEqual(
                    422, resp.status_code,
                    "%s 对不达标内容应返回 422，实际 %s" % (path, resp.status_code),
                )
                body = resp.get_json() or {}
                self.assertEqual("quality_fail", body.get("code"), path)
                self.assertIn("score", body, path)

    # ---------- 3. 纯文本导出不误伤 ----------
    def test_plain_text_export_is_not_blocked(self):
        with app_module.app.test_request_context("/"):
            guard = app_module._export_gate_guard({"text": "任意正文", "mode": "fast"})
        self.assertIsNone(guard, "没有 history_id 时不应拦截纯文本导出")


if __name__ == "__main__":
    unittest.main(verbosity=2)
