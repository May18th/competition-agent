# -*- coding: utf-8 -*-
"""417轮探针：PPT 大纲 N 页 -> deck 几页？定位 16->8 的断点"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from rich_pipeline import _outline_deck, _clean_deck_slides

PAGES = ['封面', '痛点与问题量化', '现有方案不足', '我们的方案', '核心技术',
         '创新点', '市场与用户', '商业模式', '竞品对比', '竞争壁垒',
         '落地进展与实测', '社会价值', '团队与分工', '财务测算',
         '发展规划', '愿景与致谢']

VARIANTS = {
    'A_井号序号': "\n\n".join(
        "## %d. %s\n\n- 要点一：具体数据\n- 要点二：具体场景\n\n讲解稿：这一页要讲清楚%s。"
        % (i, p, p) for i, p in enumerate(PAGES, 1)),
    'B_第N页': "\n\n".join(
        "## 第%d页 %s\n\n- 要点一\n- 要点二\n\n讲解稿：%s说明。" % (i, p, p)
        for i, p in enumerate(PAGES, 1)),
    'C_纯数字点': "\n\n".join(
        "%d. %s\n\n- 要点一\n- 要点二" % (i, p) for i, p in enumerate(PAGES, 1)),
    'D_井号无序号': "\n\n".join(
        "## %s\n\n- 要点一\n- 要点二" % p for p in PAGES),
}

for name, outline in VARIANTS.items():
    d = _outline_deck(outline)
    slides = d.get("slides") or []
    print("[%s] 大纲 %d 页 -> 解析出 %d 页" % (name, len(PAGES), len(slides)))
    if len(slides) != len(PAGES):
        titles = [s.get("title", "")[:14] for s in slides]
        print("     解析到的标题：", titles)
    else:
        print("     首末页：", slides[0].get("title", "")[:12], "|", slides[-1].get("title", "")[:12])

# 再看 build_rich_assets 的截断与封面插入会不会改变页数
import re
d = _outline_deck(VARIANTS['A_井号序号'])
slides = d["slides"]
norm = list(slides[:18])
print("\n截断 slides[:18] 后：", len(norm), "页（大纲", len(PAGES), "页）")
if norm and norm[0].get("type") != "cover":
    norm.insert(0, {"type": "cover"})
    print("又 insert 了一个 cover ->", len(norm), "页（这是 +1 的元凶）")
