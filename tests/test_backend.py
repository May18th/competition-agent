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


class TestPendingSection(unittest.TestCase):
    """模型自造的「待替换数据清单」必须整节删掉，不能留给评委。"""

    def test_removes_pending_section(self):
        src = ("## 八、财务分析\n正文数字若干。\n"
               "## 待替换数据清单\n- 单台售价 1.8 万元 → 替换为真实报价\n- 首年营收 20 万元 → 替换为财务表\n")
        out = ca._strip_pending_sections(src)
        self.assertNotIn("待替换", out)
        self.assertIn("## 八、财务分析", out)
        self.assertIn("正文数字若干", out)

    def test_keeps_following_section(self):
        src = ("## 待补充材料\n- 专利受理号\n## 九、风险分析\n技术风险与应对。\n")
        out = ca._strip_pending_sections(src)
        self.assertNotIn("待补充", out)
        self.assertIn("## 九、风险分析", out)
        self.assertIn("技术风险与应对", out)

    def test_normal_headings_untouched(self):
        src = "## 一、项目背景\n## 二、风险分析与应对\n## 三、佐证材料清单\n"
        self.assertEqual(ca._strip_pending_sections(src), src)

    def test_dangling_reference_removed(self):
        """章节删了，正文里指向它的引用也得删——留着就是指向不存在的内容。

        实测（深度版）：正文写「替换口径见待替换数据清单」，而那一节已被清理掉。
        """
        src = ("## 十一、发展规划\n阶段目标以季度复盘为准，替换口径见待替换数据清单。\n\n"
               "## 待替换数据清单\n- 95% → 替换为实测\n")
        out = ca._strip_pending_sections(src)
        self.assertNotIn("清单", out)
        self.assertIn("阶段目标以季度复盘为准。", out)

    def test_parenthesized_reference_removed(self):
        out = ca._strip_pending_sections("## 一、摘要\n按季度复盘调整（详见待补充清单）。")
        self.assertNotIn("清单", out)
        self.assertNotIn("（）", out)
        self.assertIn("按季度复盘调整。", out)


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

    def test_no_cross_section_number_noise(self):
        """跨板块数字一致性检查已移除：口径靠正则判不准（实测 3/3 误报）。

        保留这条回归是为了防止有人把这段检查再加回来——它会稳定误报
        「单台成本 6000」vs「量产后 5000」、「毛利率 35%～45%」这类正常表述。
        """
        import quality_gate
        rec = self._fast_payload()
        rec["business_model"] = ("单台物料成本约6000至9000元。量产500台后成本降到5000元以内，"
                                 "毛利率35%至45%。")
        rec["tech_solution"] = "客单价 3.5 万元，首年总成本 75 万元。"
        _, issues = quality_gate.check_total(rec, "fast")
        self.assertFalse(any("冲突" in i for i in issues), issues)


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


class TestBlindLeakDetection(unittest.TestCase):
    """双盲否决要认人名，不能把职位描述当成姓名（实测误杀整批评测）。

    旧判据是「职位词 + 任意 2~4 字」，于是
    `负责人为材料科学与工程学院本科生`、`指导教师为…高级工程师`、`导师经费出钱`
    全被判成泄露——评测基准 3 份裸写稿 3/3 误杀，深度版 1 份同样，导出会被 422 拒。
    """

    def test_role_description_not_leak(self):
        from quality_gate import _name_leak
        for text in ("项目负责人为材料科学与工程学院本科生",
                     "指导教师为实验室与设备管理处高级工程师",
                     "技术负责人具备计算机视觉与嵌入式开发经验",
                     "硬件负责人熟悉AR光学模组与电路设计",
                     "试剂耗材由导师经费出钱",
                     "负责人为公司法定代表人"):
            self.assertFalse(_name_leak(text), text)

    def test_real_name_is_leak(self):
        from quality_gate import _name_leak
        for text in ("指导教师：张伟", "项目负责人：本项目由三人完成".replace("本项目由三人完成", "李明"),
                     "指导教师张伟，负责算法联调", "队长王小明负责统筹"):
            self.assertTrue(_name_leak(text), text)

    def test_university_name_still_leak(self):
        import quality_gate
        score, _, reasons = quality_gate.score_export(
            {"proposal": "## 一、背景\n本项目来自某某科技大学实验室。"}, "fast")
        self.assertEqual(score, 0)
        self.assertTrue(any("双盲" in r for r in reasons), reasons)

    def test_strict_false_keeps_reason_but_scores(self):
        """评测口径：否决原因照记，但不归零——否则裸写组全部 0 分，对照列没有区分度。"""
        import quality_gate
        rec = {"proposal": "## 一、背景\n" + "本项目的痛点是实验室耗材盘点耗时约4小时。" * 12}
        strict_score, _, strict_reasons = quality_gate.score_export(rec, "fast")
        soft_score, dims, soft_reasons = quality_gate.score_export(rec, "fast", strict=False)
        self.assertEqual(strict_score, soft_score)          # 没有否决项时两者一致
        self.assertEqual(strict_reasons, soft_reasons)

        leaky = {"proposal": rec["proposal"] + "\n指导教师：张伟"}
        s1, _, r1 = quality_gate.score_export(leaky, "fast")
        s2, _, r2 = quality_gate.score_export(leaky, "fast", strict=False)
        self.assertEqual(s1, 0)
        self.assertGreater(s2, 0)
        self.assertTrue(any("双盲" in x for x in r1))
        self.assertTrue(any("双盲" in x for x in r2))


if __name__ == "__main__":
    unittest.main()
