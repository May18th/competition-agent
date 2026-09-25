# -*- coding: utf-8 -*-
"""纯函数单元测试（零消费，不调 DeepSeek）

运行方式：
    python -m unittest test_backend -v
"""
import unittest
import competition_agents as ca


class TestCompetitionMatch(unittest.TestCase):
    def test_full_name_match(self):
        self.assertTrue(ca._competition_match("iCAN大赛", "iCAN大学生创新创业大赛"))
        self.assertTrue(ca._competition_match("互联网+大赛", "中国国际互联网+大学生创新创业大赛"))

    def test_alias_match(self):
        self.assertTrue(ca._competition_match("国创项目", "国家级大学生创新创业训练计划"))
        self.assertTrue(ca._competition_match("挑战杯", "大挑"))

    def test_no_match(self):
        self.assertFalse(ca._competition_match("iCAN大赛", "数学建模"))
        self.assertFalse(ca._competition_match("", "xxx"))


class TestParseKnowledge(unittest.TestCase):
    def test_parse_sections(self):
        content = "# 测试比赛\n\n## 比赛介绍\n这是介绍\n\n## 评分标准\n- 创新性：30%\n\n## 偏好方向\n- 硬科技\n"
        r = ca.parse_knowledge(content)
        self.assertEqual(r["title"], "测试比赛")
        self.assertIn("创新性", r["scoring"])
        self.assertIn("硬科技", r["preference"])
        self.assertEqual(r["sections"], "")
        self.assertEqual(r["penalty"], "")


class TestKnowledgeFormat(unittest.TestCase):
    def test_complete(self):
        c = "介绍 比赛 评分标准 申报书 章节 偏好 方向 扣分点"
        self.assertTrue(ca.check_knowledge_format(c)["ok"])

    def test_incomplete(self):
        c = "只有比赛介绍"
        r = ca.check_knowledge_format(c)
        self.assertFalse(r["ok"])
        self.assertIn("评分标准", r["missing"])


class TestProposalCompleteness(unittest.TestCase):
    def test_complete(self):
        p = "项目背景：痛点。解决方案：xx。技术路线：xx。创新：xx。商业模式：xx。风险：xx。社会价值与应用前景：xx"
        self.assertTrue(ca.check_proposal_completeness(p)["ok"])

    def test_incomplete(self):
        r = ca.check_proposal_completeness("我们做了个产品")
        self.assertFalse(r["ok"])
        self.assertIn("项目背景", r["missing"])


class TestShouldIterate(unittest.TestCase):
    def test_approved(self):
        self.assertEqual(ca.should_iterate({"approved": True, "revision_count": 1}), "defense")

    def test_low_score_first(self):
        self.assertEqual(ca.should_iterate({"approved": False, "revision_count": 1}), "revise")

    def test_max_iterations(self):
        self.assertEqual(ca.should_iterate({"approved": False, "revision_count": 2}), "defense")


class TestShouldIterateFast(unittest.TestCase):
    def test_off(self):
        self.assertEqual(ca.should_iterate_fast({"iterate": False, "approved": False, "revision_count": 1}), "defense")

    def test_on_low_score(self):
        self.assertEqual(ca.should_iterate_fast({"iterate": True, "approved": False, "revision_count": 1}), "revise")

    def test_on_approved(self):
        self.assertEqual(ca.should_iterate_fast({"iterate": True, "approved": True, "revision_count": 1}), "defense")

    def test_on_max(self):
        self.assertEqual(ca.should_iterate_fast({"iterate": True, "approved": False, "revision_count": 2}), "defense")


class TestQuotaStatus(unittest.TestCase):
    def test_fields(self):
        st = ca.get_quota_status()
        for k in ["date", "calls", "limit", "remaining", "exceeded"]:
            self.assertIn(k, st)


if __name__ == "__main__":
    unittest.main()
