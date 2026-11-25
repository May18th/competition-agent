# -*- coding: utf-8 -*-
"""篇幅收敛（_wb_len_trim）单元测试。

背景：简洁版最终闸门先让模型压（目标 1780），模型「压不动」时会停在略超的位置（实测 1830）。
差几十字再花一次 LLM 调用不划算，所以由代码按句末标点整句从尾部删除。
这里覆盖四条边界：不超标、轻微超标、超出 5% 以上、极端文本。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import _wb_len_trim


def _sent(n_chars, idx):
    """构造一句 n_chars 个汉字 + 句号的句子（句号计入字数，与 _cjk_len 口径一致）。"""
    return ("句" * (n_chars - 4) + "%03d" % idx + "。")


def _make(sentences, per=30):
    return "".join(_sent(per, i) for i in range(sentences))


class TestLenTrim(unittest.TestCase):
    def test_no_trim_when_within_cap(self):
        text = _make(20)                      # 20 × 30 = 600 字
        out, cut = _wb_len_trim(text, 1800)
        self.assertEqual(out, text)
        self.assertEqual(cut, 0)

    def test_trims_slight_overshoot_to_cap(self):
        text = _make(61)                      # 61 × 30 = 1830 字（实测同款落点）
        out, cut = _wb_len_trim(text, 1800)
        self.assertGreater(cut, 0)
        self.assertLessEqual(len(out.replace("\n", "")), 1800)
        self.assertTrue(out.endswith("。"), "必须按整句裁剪，不能断在半句")
        # 只应删掉末尾 1 句，不该大改正文
        self.assertEqual(len(text) - len(out), 30)
        self.assertGreater(len(out), 1800 * 0.9)

    def test_refuses_when_way_over_cap(self):
        text = _make(100)                     # 3000 字，超 66%
        out, cut = _wb_len_trim(text, 1800)
        self.assertEqual(out, text, "超出 5% 以上不硬裁，交给 LLM 压")
        self.assertEqual(cut, 0)

    def test_refuses_when_single_huge_sentence(self):
        text = "巨" * 2400                    # 没有任何句末标点，无法整句裁
        out, cut = _wb_len_trim(text, 1800)
        self.assertEqual(cut, 0)
        self.assertEqual(out, text)

    def test_keeps_markdown_structural_lines(self):
        body = "## 一、项目背景\n" + _make(50) + "\n## 二、技术方案\n" + _make(11)
        out, cut = _wb_len_trim(body, 1800)
        self.assertGreater(cut, 0)
        self.assertIn("## 一、项目背景", out, "标题不能被裁掉")


if __name__ == "__main__":
    unittest.main()
