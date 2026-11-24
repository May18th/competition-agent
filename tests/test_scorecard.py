# -*- coding: utf-8 -*-
"""评分项诊断台的判据回归。

这些用例都来自实测踩过的坑，不是为覆盖率凑的：
否定句被读成正面证据、数字在关键词前面漏检、同族维度把同一缺口报两遍。
"""

import unittest

from backend import scorecard as sc


_PROFILE_COMP = "中国国际互联网+大学生创新创业大赛"   # 个人成长30/项目创新30/产业价值25/团队协作15
_NO_WEIGHT_COMP = "蓝桥杯全国软件和信息技术专业人才大赛"  # 只有机考项，权重为 None


def _payload(proposal, **kw):
    rec = {"proposal": proposal}
    rec.update(kw)
    return rec


class TestDimensionClassify(unittest.TestCase):
    def test_known_dimensions(self):
        cases = {
            "创新性": "innovation",
            "原创性": "innovation",
            "模型创造性": "innovation",
            "模型假设合理性": "feasibility",
            "结果检验、灵敏度分析": "feasibility",
            "技术实现（架构、代码、软件工程）": "tech",
            "作品功能指标完成度": "tech",
            "产业价值": "business",
            "社会价值": "social",
            "综合答辩与展示": "presentation",
            "论文规范与表达": "presentation",
            "团队协作": "team",
            "个人成长": "team",
            "实用价值与应用前景": "value",
        }
        for name, want in cases.items():
            self.assertEqual(sc.classify_dim(name), want, name)

    def test_unknown_falls_back_to_general(self):
        self.assertEqual(sc.classify_dim("软件类机考（OJ机器自动评分）"), "general")


class TestDiagnoseContract(unittest.TestCase):
    def test_no_weight_competition_is_not_diagnosed(self):
        diag = sc.diagnose(_payload("随便写点正文" * 100), _NO_WEIGHT_COMP)
        self.assertFalse(diag["available"])
        self.assertEqual(diag["dims"], [])
        self.assertIsNone(diag["total"])
        self.assertIn("未配置官方评分权重", diag["reason"])

    def test_every_check_carries_evidence_or_gap(self):
        """通过项要有判据说明（能引用原文就带片段），未通过项必须进缺口清单。"""
        diag = sc.diagnose(_payload("## 一、执行摘要\n本项目做一个试剂盘点柜。" * 20),
                           _PROFILE_COMP)
        self.assertTrue(diag["available"])
        for dim in diag["dims"]:
            gap_labels = {g.split("：")[0] for g in dim["gaps"]}
            for c in dim["checks"]:
                self.assertTrue(c["note"], (dim["name"], c["key"]))
                if c["status"] != "pass":
                    self.assertIn(c["label"], gap_labels, (dim["name"], c["key"]))

    def test_general_family_excluded_from_total(self):
        """归不进判据族的维度不计入总分，否则等于用猜的分充数。"""
        diag = sc.diagnose(_payload("## 一、执行摘要\n" + "内容" * 500),
                           "全国大学生广告艺术大赛")
        by_name = {d["name"]: d for d in diag["dims"]}
        if "主题契合" in by_name:
            self.assertFalse(by_name["主题契合"]["judged"])
            self.assertLess(diag["full_mark"], sum(d["weight"] for d in diag["dims"]))


class TestPositiveEvidence(unittest.TestCase):
    def test_negated_patent_is_not_evidence(self):
        """「不存在高门槛专利壁垒」是「没有专利」，不能算成有专利。"""
        text = ("## 一、执行摘要\n柜体结构加称重与视觉的方案不存在高门槛专利壁垒，"
                "大厂可能在12至18个月内跟进。")
        diag = sc.diagnose(_payload(text), "iCAN大学生创新创业大赛")
        dim = next(d for d in diag["dims"] if d["name"] == "创新性")
        check = next(c for c in dim["checks"] if c["key"] == "novelty_evidence")
        self.assertNotEqual(check["status"], "pass", check)

    def test_number_before_keyword_counts(self):
        """「3所高校6个课题组」数字在前，也要算客户规模证据。"""
        text = ("## 一、执行摘要\n目标在3所高校6个课题组试点，把月底对账自动化。"
                "单台物料成本约1.8万元。")
        diag = sc.diagnose(_payload(text), "互联网+")
        dim = next(d for d in diag["dims"] if d["name"] == "产业价值")
        check = next(c for c in dim["checks"] if c["key"] == "market_size")
        self.assertEqual(check["status"], "pass", check)

    def test_acceptance_baseline_is_not_a_benchmark(self):
        """「验收基线」是自家指标，不是对比实验基线。"""
        text = ("## 一、技术方案\n三阶段验收指标与验收基线如下：准确率不低于85%。")
        diag = sc.diagnose(_payload(text), "互联网+")
        dim = next(d for d in diag["dims"] if d["name"] == "项目创新")
        check = next(c for c in dim["checks"] if c["key"] == "novelty_evidence")
        self.assertNotEqual(check["status"], "pass", check)


    def test_improvement_style_comparison_counts_as_partial(self):
        """「把误记率从纯称重方案的 8% 压到 3%」是真对比，只是没用「相比」二字。"""
        text = ("## 三、技术方案\n双校验把误记率从纯称重方案的约 8% 压到 3% 以内，"
                "解决了同一瓶被换内容物导致称重误判的问题。")
        diag = sc.diagnose(_payload(text), "互联网+")
        dim = next(d for d in diag["dims"] if d["name"] == "项目创新")
        check = next(c for c in dim["checks"] if c["key"] == "diff_statement")
        self.assertEqual(check["status"], "partial", check)
        self.assertTrue(check["snippet"])

    def test_named_innovation_counts_as_partial(self):
        """「双校验」这类命名式创新算部分覆盖，但不算集中列出创新点。"""
        diag = sc.diagnose(_payload("## 一、执行摘要\n做称重+视觉双校验的智能盘点柜。"), "互联网+")
        dim = next(d for d in diag["dims"] if d["name"] == "项目创新")
        check = next(c for c in dim["checks"] if c["key"] == "innovation_points")
        self.assertEqual(check["status"], "partial", check)

    def test_weekly_sync_meeting_is_collaboration(self):
        """「团队每周一次联调会」就是协作机制，不能因为没写「例会」二字判缺失。"""
        text = ("## 七、创业团队\n硬件成员负责选型，算法成员负责模型训练。"
                "团队每周一次联调会，按硬件、算法、后台三条线并行推进。")
        diag = sc.diagnose(_payload(text), "互联网+")
        dim = next(d for d in diag["dims"] if d["name"] == "团队协作")
        check = next(c for c in dim["checks"] if c["key"] == "collaboration")
        self.assertEqual(check["status"], "pass", check)


class TestGapAggregation(unittest.TestCase):
    def test_same_gap_across_family_dims_reported_once(self):
        """「个人成长」「团队协作」同属 team 族，同一缺口只报一条并合并丢分。"""
        diag = sc.diagnose(_payload("## 一、执行摘要\n本项目做一个柜子。" * 30),
                           _PROFILE_COMP)
        gaps = [g["gap"] for g in diag["top_gaps"]]
        self.assertEqual(len(gaps), len(set(gaps)), gaps)

    def test_top_gaps_sorted_by_loss(self):
        diag = sc.diagnose(_payload("## 一、执行摘要\n本项目做一个柜子。" * 30),
                           _PROFILE_COMP)
        lost = [g["lost"] for g in diag["top_gaps"]]
        self.assertEqual(lost, sorted(lost, reverse=True))


class TestRevisionNote(unittest.TestCase):
    def test_revision_note_stripped_before_diagnose(self):
        """hid 24 的形态：正文第一页是「修订说明 + 针对意见(n)」，诊断前必须清掉。"""
        from backend.competition_agents import _strip_revision_note
        text = ("# 修订说明\n\n本次修订严格对应评委意见的六条。\n\n"
                "1. **针对意见（1）**：在技术方案后新增预实验小节。\n\n"
                "## 一、执行摘要\n本项目做一台试剂盘点柜，单台成本约1.8万元。\n"
                "## 二、项目背景\n实验室台账靠手抄，月底对不上账。")
        out = _strip_revision_note(text)
        self.assertTrue(out.startswith("## 一、执行摘要"), out[:30])
        self.assertNotIn("针对意见", out)

    def test_plain_proposal_untouched(self):
        from backend.competition_agents import _strip_revision_note
        src = "## 一、执行摘要\n本项目做一台试剂盘点柜。"
        self.assertEqual(_strip_revision_note(src), src)


if __name__ == "__main__":
    unittest.main()
