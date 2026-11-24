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


class TestStripCliches(unittest.TestCase):
    """套话替换：评分表的扣分项要在生成收尾就清掉，不能留给导出时警告用户自己改。"""

    def test_replaces_common_cliches(self):
        out = ca._strip_cliches("形成闭环，赋能产业，找准抓手")
        for bad in ("闭环", "赋能", "抓手"):
            self.assertNotIn(bad, out)
        self.assertIn("完整流程", out)

    def test_long_phrase_wins(self):
        # 先长后短：不能先把「形成闭环」拆成「形成完整流程」再二次替换
        self.assertEqual(ca._strip_cliches("形成闭环"), "形成完整流程")

    def test_idempotent(self):
        once = ca._strip_cliches("赋能与抓手，进一步提升")
        self.assertEqual(ca._strip_cliches(once), once)

    def test_empty_and_untouched_text(self):
        self.assertEqual(ca._strip_cliches(""), "")
        src = "基于称重传感器的耗材盘点柜，实测误差 2.3%"
        self.assertEqual(ca._strip_cliches(src), src)


class TestPendingCitation(unittest.TestCase):
    """半成品引用：评委看到「待补充」等于承认没查证，评分表直接算占位符。"""

    def test_keeps_verifiable_part(self):
        src = "约 2～4 万元/台（行业公开数据，2024，来源待补充具体出处），大件适配差"
        out = ca._strip_ai_artifacts(src)
        self.assertNotIn("待补充", out)
        self.assertIn("（行业公开数据，2024）", out)
        self.assertIn("大件适配差", out)

    def test_drops_whole_bracket_when_nothing_left(self):
        out = ca._strip_ai_artifacts("单台成本（具体金额待补充核实）约 3 万元")
        self.assertNotIn("待补充", out)
        self.assertIn("单台成本约 3 万元", out)

    def test_quoted_critique_untouched(self):
        # 评委意见里「标注为"待补充核实"」是对正文的引用，不带括号，不能被改坏
        src = '评委指出：关键数据来源标注为"待补充核实"，削弱论证'
        self.assertEqual(ca._strip_ai_artifacts(src), src)


class TestQualityGateMode(unittest.TestCase):
    """简洁版不能被深度版口径判不合格：否则每次生成都刷三条固定噪声。"""

    def _fast_payload(self):
        body = "本节给出实测数据 100 万元，采用算法模型验证口径。" * 20
        return {
            "parsed_rules": "x", "similarity_report": "x", "competitor_analysis": "x",
            "business_model": "x", "risk_analysis": "x", "tech_solution": "x",
            "proposal": "## 一、项目背景\n" + body,
            "judge_feedback": "x", "defense_questions": "x", "ppt_outline": "x",
            "speech_script": "x",
        }

    def test_fast_skips_deep_only_modules(self):
        import quality_gate
        _, issues = quality_gate.check_total(self._fast_payload(), "fast")
        for m in ("implementation_plan", "social_value", "project_summary"):
            self.assertFalse(any(m in i for i in issues), (m, issues))

    def test_deep_still_requires_them(self):
        import quality_gate
        _, issues = quality_gate.check_total(self._fast_payload(), "deep")
        self.assertTrue(any("implementation_plan" in i for i in issues), issues)

    def test_fast_skips_rich_media(self):
        import quality_gate
        _, issues = quality_gate.check_generation(self._fast_payload(), "fast")
        self.assertFalse(any("富媒体" in i for i in issues), issues)

    def test_deep_requires_rich_media(self):
        import quality_gate
        _, issues = quality_gate.check_generation(self._fast_payload(), "deep")
        self.assertTrue(any("富媒体" in i for i in issues), issues)


class TestDeidentChainSafety(unittest.TestCase):
    """清理链不能自己造出违规表述（实测踩过：删括号残留「指导教师+后文」被判双盲）。"""

    def test_teacher_placeholder_merged_not_stripped(self):
        out = ca._strip_ai_artifacts("项目指导教师（某老师）路线与答辩")
        self.assertEqual(out, "项目指导人员路线与答辩")
        self.assertNotIn("指导教师", out)

    def test_result_not_flagged_as_blind_leak(self):
        import quality_gate
        out = ca._strip_ai_artifacts("项目指导教师（某老师）路线与答辩")
        _, _, reasons = quality_gate.score_export({"proposal": out}, "fast")[:3]
        self.assertFalse(any("双盲" in r for r in reasons), reasons)

    def test_jtbd_not_treated_as_placeholder(self):
        import quality_gate
        _, _, reasons = quality_gate.score_export(
            {"proposal": "**技术名词**：用户旅程地图、JTBD、角色权限模型 RBAC"}, "fast")[:3]
        self.assertFalse(any("占位符" in r for r in reasons), reasons)


if __name__ == "__main__":
    unittest.main()
