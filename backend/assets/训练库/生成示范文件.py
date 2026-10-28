# -*- coding: utf-8 -*-
"""第176轮：批量生成规范示范文件（自建原创，AI生成·经人工确认·规范示范）。
不依赖 LLM，按赛事官方章节结构 + 自建范式生成结构规范的示范 .docx/.pptx。
仅用于训练导出结构与排版，不代表真实项目，不含任何真实个人信息。
用法：python 训练库/生成示范文件.py [--all]
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from docx_render import build_docx  # noqa: E402
from pptx_builder import build_deck  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LABEL = "AI生成 · 经人工确认 · 规范示范"

DECK_STRUCTURE = [
    ("项目封面", "cover", []),
    ("项目背景与痛点", "bullets", ["目标场景一句话", "现有方案核心短板", "本项目要解决的矛盾"]),
    ("解决方案", "bullets", ["核心功能与运行机制", "与现有方案差异点", "关键量化指标"]),
    ("技术方案", "bullets", ["整体技术架构", "核心技术难点与突破", "AI 的核心作用"]),
    ("商业模式", "bullets", ["目标用户与付费意愿", "收入来源结构", "成本与落地路径"]),
    ("团队与里程碑", "bullets", ["团队分工与专长", "当前进展", "后续 6-12 个月里程碑"]),
    ("结尾", "section", []),
]


def load_profiles():
    p = os.path.join(ROOT, "assets", "data", "competition_profiles.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)["competitions"]


def safe(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def sample_docx_md(comp, kind):
    chapters = comp.get("chapters") or ["项目概述", "创新点", "技术方案", "实施计划", "预期成果"]
    lines = ["# %s（规范示范·%s）" % (comp["name"], kind), ""]
    lines.append("> 本文件为自建原创规范示范：%s。仅用于训练导出结构与排版，不代表真实项目。" % LABEL)
    lines.append("")
    for ch in chapters:
        lines.append("## " + ch)
        lines.append("")
        lines.append("（规范示范内容：本章围绕该章节展开，含具体场景、数据口径与证据；示例数据已标注「示例数据，非真实」。）")
        lines.append("")
    return "\n".join(lines)


def gen_docx(comp, kind, doc_type):
    title = "%s（规范示范·%s）" % (comp["name"], kind)
    md = sample_docx_md(comp, kind)
    doc = build_docx(title, md, subtitle=LABEL, doc_type=doc_type, toc=True)
    d = os.path.join(BASE, safe(comp["name"]), kind)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "%s_%s_规范示范.docx" % (safe(comp["name"]), kind))
    doc.save(out)
    return out


def gen_pptx(comp):
    deck = {
        "project": "%s 规范示范项目" % comp["name"],
        "one_liner": "自建原创规范示范 · 仅用于训练 PPT 版式与讲解稿备注",
        "competition": comp["name"],
        "slides": [],
    }
    for title, typ, bullets in DECK_STRUCTURE:
        slide = {
            "type": typ,
            "title": title,
            "bullets": list(bullets),
            "note": "讲解稿（规范示范）：%s。本页要点式呈现，现场讲解控制 20-40 秒。" % title,
        }
        deck["slides"].append(slide)
    d = os.path.join(BASE, safe(comp["name"]), "路演PPT")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "%s_路演PPT_规范示范.pptx" % safe(comp["name"]))
    build_deck(deck, out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="生成全部 15 赛事（默认只 iCAN + 互联网+）")
    args = ap.parse_args()
    comps = load_profiles()
    if not args.all:
        comps = [c for c in comps if ("iCAN" in c["name"] or "互联网" in c["name"])][:2]
    files = []
    for c in comps:
        files.append(gen_docx(c, "申报书", "default"))
        files.append(gen_docx(c, "说明书", "report"))
        files.append(gen_pptx(c))
    meta = {"count": len(files), "files": files, "note": LABEL}
    with open(os.path.join(BASE, "元数据.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("生成 %d 份示范文件" % len(files))
    for f in files:
        print("  ", os.path.relpath(f, ROOT))


if __name__ == "__main__":
    main()

