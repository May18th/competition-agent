#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""417 轮探针：PDF 页数/体积按赛事校验（真生成 PDF，不 mock）"""
import os
import sys

from pdf_render import render_markdown_to_pdf
from quality_gate import check_pdf, pdf_limits_for

SHORT = """# 项目概述

本项目面向校园快递最后一公里，已在 3 所高校试点。

## 核心数据

试点准确率 96.2%，单件成本下降 31%。
"""

LONG_PARTS = ["# 作品说明书\n"]
for i in range(1, 31):
    _filler = "".join("（{}-{}）该行用于占位，验证长文分页是否按预期落页。\n\n".format(i, k)
                      for k in range(1, 14))
    LONG_PARTS.append(
        ("\n## 第 %d 章 章节标题\n\n"
         "本章说明第 %d 部分的研究内容与方法，包含测算过程、数据口径与结论，"
         "用于评审专家核对正文完整性。\n\n"
         "测算依据：基于试点样本 n=128，置信区间 95%%，误差范围 ±3.2%%。\n"
         "结论：该部分指标达到预期目标，具备推广条件。\n" % (i, i)) + _filler
    )
LONG = "".join(LONG_PARTS)


def run(name, text):
    path = "_probe_417_%s.pdf" % name
    render_markdown_to_pdf(text, path, title=name)
    mb = round(os.path.getsize(path) / (1024.0 * 1024.0), 2)
    print("\n=========== %s （%.2fMB） ===========" % (name, mb))

    # A) 向后兼容：不传赛事，2 元组
    ok, issues = check_pdf(path)
    print("[兼容] 返回类型=%s ok=%s issues=%s" % (type(ok).__name__, ok, issues))

    # B) iCAN
    d = check_pdf(path, competition_name="iCAN 大学生创新创业大赛", doc_title="作品说明书", detail=True)
    print("[iCAN] %s" % pdf_limits_for("iCAN 大学生创新创业大赛", "作品说明书"))
    print("[iCAN] pages=%s mb=%s ok=%s" % (d["pages"], d["mb"], d["ok"]))
    for e in d["errors"]:
        print("   ERR:", e)
    for w in d["warnings"]:
        print("   WARN:", w)
    for s in d["suggestions"]:
        print("   TIP:", s)

    # C) 未知赛事：应走宽松默认，不误杀
    d2 = check_pdf(path, competition_name="某某校内选拔赛", doc_title="申报书", detail=True)
    print("[未知赛事] limit=%s ok=%s errors=%s" % (d2["limit"], d2["ok"], d2["errors"]))


if __name__ == "__main__":
    run("short", SHORT)
    run("long", LONG)
    # 直接验建议分支（体积超限 / 大幅超页），不必真造出一个 10MB 的 PDF
    from quality_gate import _pdf_trim_suggestions
    lim = pdf_limits_for("iCAN", "作品说明书")
    print("\n--- 合成：28 页 / 13.4MB / iCAN ---")
    for t in _pdf_trim_suggestions(28, 13.4, lim):
        print("   TIP:", t)
    print("\nDONE")
