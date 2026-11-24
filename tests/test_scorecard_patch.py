# -*- coding: utf-8 -*-
"""定向补写的回归。重点测三件事：
事实类缺口不能交给模型补、同章缺口要合并、补完没涨分必须回退。
"""

import unittest

from backend import scorecard_patch as sp


_PROFILE_COMP = "中国国际互联网+大学生创新创业大赛"

# 一份刻意缺「成长叙述」与「差异化对比」的正文
_BASE = """## 一、执行摘要
本项目做试剂盘点柜，单台成本约1.2万元，年服务费约6000元。

## 三、产品/技术方案
柜体用称重传感器判断取放，摄像头识别瓶身标签，双校验降低误记。

## 七、创业团队
硬件成员负责选型，算法成员负责模型训练，运营成员负责访谈。团队每周一次联调会。

## 九、风险分析与应对方案
视觉识别在深色瓶上准确率下降，应对是补光加多角度拍摄。
"""


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """按调用顺序返回预设内容，并记录收到的 prompt。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return _FakeResp(self.replies.pop(0) if self.replies else "")


class TestLocateChapter(unittest.TestCase):
    def test_hits_matching_chapter(self):
        # 成长 → 团队章
        self.assertIn("创业团队", sp.locate_chapter(_BASE, "成长与收获")["title"])
        # 差异化 → 技术方案章
        self.assertIn("技术方案", sp.locate_chapter(_BASE, "差异化对比陈述")["title"])
        # 风险应对 → 风险章
        self.assertIn("风险", sp.locate_chapter(_BASE, "风险与应对")["title"])

    def test_unknown_gap_falls_back_without_appendix(self):
        got = sp.locate_chapter(_BASE, "某个没登记的缺口")
        self.assertTrue(got.get("fallback"))
        self.assertNotIn("附录", got["title"])


class TestPlanPatches(unittest.TestCase):
    def _diag(self):
        from backend.scorecard import diagnose
        return diagnose({"proposal": _BASE}, _PROFILE_COMP, None, "fast")

    def test_fact_gaps_are_not_delegated(self):
        """新颖性要的是真实专利/查新，模型补只会编，直接跳过（也不提醒用户）。"""
        info = sp.plan_patches(self._diag(), _BASE)
        labels = [p["label"] for p in info]
        self.assertFalse(any("新颖性" in l for l in labels), labels)

    def test_same_chapter_merged_into_one_task(self):
        """成长与收获/协作机制同属团队章，只能安排一次补写。"""
        info = sp.plan_patches(self._diag(), _BASE)
        chapters = [p["chapter"] for p in info]
        self.assertEqual(len(chapters), len(set(chapters)), chapters)

    def test_plan_sorted_by_loss(self):
        info = sp.plan_patches(self._diag(), _BASE, limit=3)
        lost = [p["lost"] for p in info]
        self.assertEqual(lost, sorted(lost, reverse=True))

    def test_force_label_pulls_gap_outside_top_gaps(self):
        """「创新点可数」掉出 top_gaps 前三条时，指定后仍要能补到它。

        top_gaps 只留三条，实测有整轮创新点掉出榜单 → 兜底永远不触发。
        """
        diag = self._diag()
        # 人为把 top_gaps 换成不含创新点的三条，模拟线上那种轮次
        diag["top_gaps"] = [g for g in diag["top_gaps"]
                            if "创新点" not in g["gap"]][:3]
        plain = sp.plan_patches(diag, _BASE, limit=2)
        self.assertFalse(any("创新点" in p["label"] for p in plain), plain)

        forced = sp.plan_patches(diag, _BASE, limit=2, force_labels=("创新点可数",))
        self.assertTrue(any("创新点" in p["label"] for p in forced), forced)
        self.assertIn("创新点", forced[0]["label"])      # 指定项排在最前


class TestRewriteChapter(unittest.TestCase):
    def test_other_chapters_untouched(self):
        patch = {"chapter": "## 七、创业团队", "instruction": "补成长叙述"}
        new_ch = ("## 七、创业团队\n硬件成员负责选型，算法成员负责模型训练。"
                  "成员在其中掌握了传感器标定方法，积累了小样本训练经验，"
                  "也熟悉了课题组访谈与试点对接的完整流程。")
        out, ok = sp.rewrite_chapter(_BASE, patch, llm=_FakeLLM([new_ch]))
        self.assertTrue(ok)
        self.assertIn("## 九、风险分析与应对方案", out)
        self.assertIn("补光加多角度拍摄", out)          # 其它章原样保留
        self.assertIn("掌握了传感器标定方法", out)

    def test_line_shift_does_not_break_locating(self):
        """第一次补写改变行数后，第二次仍要按标题定位，不能按旧行号切片。"""
        p1 = {"chapter": "## 三、产品/技术方案", "instruction": "补对比"}
        long_ch = "## 三、产品/技术方案\n" + "称重加视觉双校验，误记率从8%压到3%。\n" * 8
        p2 = {"chapter": "## 七、创业团队", "instruction": "补成长"}
        team_ch = ("## 七、创业团队\n硬件成员掌握传感器标定方法，算法成员积累训练经验，"
                   "运营成员熟悉访谈流程，团队每周联调。")
        out, ok1 = sp.rewrite_chapter(_BASE, p1, llm=_FakeLLM([long_ch]))
        out, ok2 = sp.rewrite_chapter(out, p2, llm=_FakeLLM([team_ch]))
        self.assertTrue(ok1 and ok2)
        # 第二次补写要落在团队章、且风险章仍在——行号漂移时按旧行号切会把这两条都弄坏
        self.assertIn("掌握传感器标定方法", out)
        self.assertIn("## 九、风险分析", out)

    def test_short_reply_rejected(self):
        """模型只回增量片段时不能拿它替换整章。"""
        out, ok = sp.rewrite_chapter(_BASE, {"chapter": "## 七、创业团队",
                                             "instruction": "补成长"},
                                     llm=_FakeLLM(["成员掌握了方法。"]))
        self.assertFalse(ok)
        self.assertEqual(out, _BASE)


class TestPatchUntilClean(unittest.TestCase):
    def test_revert_when_no_gain(self):
        """补写没让分数上涨，必须回退到原文，不能把改坏的东西留下。"""
        # 回一段与原文相同的内容，分数不变
        same = _BASE[_BASE.find("## 七、创业团队"):_BASE.find("## 九、")]
        rep = sp.patch_until_clean({"proposal": _BASE}, _PROFILE_COMP, None, "fast",
                                   limit=1, llm=_FakeLLM([same, same]))
        self.assertEqual(rep["proposal"].strip(), _BASE.strip())
        self.assertTrue(rep["reverted"], rep)

    def test_applied_when_gain(self):
        team_ch = ("## 七、创业团队\n硬件成员负责选型，算法成员负责模型训练，运营成员负责访谈。"
                   "团队每周一次联调会，按三条线并行推进。成员在联调中掌握了传感器标定方法，"
                   "算法成员积累了小样本模型的训练与调参经验，运营成员熟悉了课题组访谈流程。")
        rep = sp.patch_until_clean({"proposal": _BASE}, _PROFILE_COMP, None, "fast",
                                   limit=1, llm=_FakeLLM([team_ch, team_ch]))
        self.assertGreater(rep["after"], rep["before"])
        self.assertTrue(rep["applied"], rep)
        self.assertIn("掌握了传感器标定方法", rep["proposal"])

    def test_dirty_input_is_cleaned_before_patch(self):
        """原文里的待办章节与套话必须先清掉再定位。

        线上 hid 323 实测：诊断读到的是清理后正文，补写却按原文定位，缺口落到
        「## 待替换数据清单」这一章上——补完正文里仍留着给评委看的待办清单。
        """
        dirty = _BASE + ("\n## 待替换数据清单\n- 成本 1.2 万 → 替换为实测数据\n"
                         "- 本方案可赋能产业链，形成闭环\n")
        rep = sp.patch_until_clean({"proposal": dirty}, _PROFILE_COMP, None, "fast",
                                   limit=1, llm=_FakeLLM([]))
        self.assertNotIn("待替换数据清单", rep["proposal"])
        self.assertNotIn("赋能", rep["proposal"])
        self.assertNotIn("闭环", rep["proposal"])
        self.assertIn("## 七、创业团队", rep["proposal"])

    def test_no_patch_plan_returns_original(self):
        rep = sp.patch_until_clean({"proposal": "## 一、执行摘要\n空"}, "蓝桥杯全国软件和信息技术专业人才大赛",
                                   None, "fast", llm=_FakeLLM([]))
        self.assertEqual(rep["applied"], [])
        self.assertEqual(rep["after"], rep["before"])


class TestInnovationTrigger(unittest.TestCase):
    """生成流程的兜底触发条件：按判据看，不按 top_gaps 榜单看。"""

    def _diag(self, text):
        from backend.scorecard import diagnose
        return diagnose({"proposal": text}, _PROFILE_COMP, None, "fast")

    def test_missing_when_no_numbered_points(self):
        self.assertTrue(sp.innovation_missing(self._diag(_BASE)))

    def test_not_missing_when_numbered(self):
        text = _BASE.replace("## 三、产品/技术方案\n",
                             "## 三、产品/技术方案\n创新有三：①称重与视觉双校验；"
                             "②领用即记账；③自动对账报告。\n")
        self.assertFalse(sp.innovation_missing(self._diag(text)))

    def test_ignores_top_gaps_ranking(self):
        """即使创新点掉出 top_gaps，触发条件也必须成立。"""
        diag = self._diag(_BASE)
        diag["top_gaps"] = [g for g in diag["top_gaps"] if "创新点" not in g["gap"]][:1]
        self.assertTrue(sp.innovation_missing(diag))


if __name__ == "__main__":
    unittest.main()
