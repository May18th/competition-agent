# -*- coding: utf-8 -*-
"""侧边聊天助手（小可）测试：确定性回答不调外部模型，可离线跑。

对齐后（2026-11-25）本地聊天子系统与线上同源：
    POST /api/chat → 规则直答(source=profile) / 报错诊断(source=diagnose) / FAQ 预设 / 模型

运行方式：
    python -m unittest tests.test_chat_assistant -v
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class TestChatDeterministic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from backend.app import app
        except Exception as exc:      # 缺依赖时跳过，不让测试卡在导入
            raise unittest.SkipTest("后端应用不可导入：%s" % exc)
        cls.client = app.test_client()

    def ask(self, message):
        resp = self.client.post("/api/chat", json={"message": message, "stream": False})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def test_name_has_no_duplicate_suffix(self):
        """「科创赛事助手智能助手」是历史笔误，不能回来。"""
        from backend.app import _CHAT_NAME
        self.assertNotIn("智能助手", _CHAT_NAME)

    def test_rule_answer_reads_official_scoring(self):
        """赛事官方维度走配置直答，并带回源链接。"""
        from backend.app import _chat_rule_answer
        text = _chat_rule_answer("评分维度是多少", "iCAN大学生创新创业大赛")
        self.assertIn("创新性", text)
        self.assertIn("来源：", text)

    def test_rule_answer_does_not_invent_weights(self):
        """蓝桥杯官方未公布权重，只能列考核方向。"""
        from backend.app import _chat_rule_answer
        text = _chat_rule_answer("评分标准", "蓝桥杯")
        self.assertIn("未公布", text)
        self.assertNotIn("None", text)

    def test_rule_answer_unknown_competition_is_silent(self):
        from backend.app import _chat_rule_answer
        self.assertEqual(_chat_rule_answer("评分维度", "不存在的比赛XYZ"), "")

    def test_diagnose_maps_chinese_error(self):
        """中文报错也要归类，别只回「请重试」。"""
        from backend.app import _chat_error_answer
        self.assertIn("限流", _chat_error_answer("生成失败了 429"))
        self.assertIn("超时", _chat_error_answer("请求超时了"))
        self.assertIn("乱码", _chat_error_answer("导出被拦了，说乱码"))

    def test_route_exposes_diagnose_source(self):
        j = self.ask("生成失败了 429")
        self.assertEqual(j.get("source"), "diagnose")

    def test_chat_routes_registered(self):
        """对齐后线上那 7 个接口本地都要在。"""
        paths = {str(r) for r in self.client.application.url_map.iter_rules()}
        for path in ("/api/chat", "/api/chat_history", "/api/chat_profile",
                     "/api/chat_clear", "/api/chat_last_gen", "/api/chat_suggest",
                     "/api/chat_apply_proofread"):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
