# -*- coding: utf-8 -*-
"""纯函数单元测试（零消费，不调任何外部模型）

运行方式：
    python -m unittest tests.test_backend -v
"""
import unittest
import competition_agents as ca


class TestCompetitionMatch(unittest.TestCase):
    """赛事名（含简称/别名）→ 赛事档案匹配。"""

    def test_full_name_match(self):
        self.assertIn("iCAN", ca.get_competition_profile("iCAN大赛")["name"])
        self.assertIn("互联网+", ca.get_competition_profile("互联网+大赛")["name"])

    def test_alias_match(self):
        self.assertIn("创新创业训练计划", ca.get_competition_profile("国创项目")["name"])
        self.assertIn("挑战杯", ca.get_competition_profile("挑战杯")["name"])

    def test_no_match(self):
        self.assertFalse(ca.get_competition_profile("不存在的比赛XYZ"))
        self.assertFalse(ca.get_competition_profile(""))


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
    """深度版：低分稿最多 3 版，其余最多 2 版；返回下一跳节点列表。"""

    def test_approved(self):
        st = {"approved": True, "revision_count": 1}
        self.assertEqual(ca.should_iterate(st), ["defense", "ppt"])

    def test_low_score_first(self):
        st = {"approved": False, "score": 40, "revision_count": 1}
        self.assertEqual(ca.should_iterate(st), ["revise"])

    def test_low_score_extra_round(self):
        st = {"approved": False, "score": 40, "revision_count": 2}
        self.assertEqual(ca.should_iterate(st), ["revise"])

    def test_max_iterations(self):
        st = {"approved": False, "score": 80, "revision_count": 2}
        self.assertEqual(ca.should_iterate(st), ["defense", "ppt"])


class TestShouldIterateFast(unittest.TestCase):
    """简洁版：默认不迭代；仅显式 iterate=True 且低分时补写。"""

    def test_off(self):
        st = {"iterate": False, "approved": False, "revision_count": 1}
        self.assertEqual(ca.should_iterate_fast(st), ["defense", "ppt"])

    def test_on_low_score(self):
        st = {"iterate": True, "approved": False, "revision_count": 1}
        self.assertEqual(ca.should_iterate_fast(st), ["revise"])

    def test_on_approved(self):
        st = {"iterate": True, "approved": True, "revision_count": 1}
        self.assertEqual(ca.should_iterate_fast(st), ["defense", "ppt"])

    def test_on_max(self):
        st = {"iterate": True, "approved": False, "revision_count": 3}
        self.assertEqual(ca.should_iterate_fast(st), ["defense", "ppt"])


class TestQuotaStatus(unittest.TestCase):
    def test_fields(self):
        st = ca.get_quota_status()
        for k in ["date", "calls", "limit", "remaining", "exceeded"]:
            self.assertIn(k, st)


if __name__ == "__main__":
    unittest.main()
