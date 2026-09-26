# -*- coding: utf-8 -*-
"""赛事知识库缺口扫描：找出哪些赛事资料不完整/非官方/是推断的，供补全参考。"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

# 出现这些词说明该块是推断/非官方口径，需要补官方原文
INFER_MARKERS = ["推断", "推测", "估计", "未标注", "未公布", "通用参考", "非官方",
                 "以上为", "合理推断", "并无", "未找到官方"]


def _split_sections(content):
    secs = {}
    cur = None
    for line in (content or "").splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in secs.items()}


def _has_section(secs, *keys):
    for name, body in secs.items():
        if any(k in name for k in keys) and body.strip():
            return name, body
    return None, ""


def competition_gap_report():
    """扫描 data/*.txt，返回缺口列表 + 汇总。"""
    gaps = []
    if not os.path.isdir(DATA_DIR):
        return {"gaps": [], "total": 0, "summary": "无 data 目录"}
    for fn in sorted(os.listdir(DATA_DIR)):
        if not fn.endswith(".txt"):
            continue
        comp = fn[:-4]
        try:
            with open(os.path.join(DATA_DIR, fn), encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        secs = _split_sections(content)
        name, body = _has_section(secs, "评分", "打分")
        scoring_gap = None
        if not name:
            scoring_gap = "无评分标准"
        elif any(m in body for m in INFER_MARKERS):
            scoring_gap = "评分是推断/非官方口径"
        _, sec_body = _has_section(secs, "章节", "申报书", "结构", "必须包含")
        section_gap = None
        if not sec_body:
            section_gap = "无申报书章节要求"
        if scoring_gap or section_gap:
            issues = [g for g in (scoring_gap, section_gap) if g]
            gaps.append({"competition": comp, "issues": issues, "chars": len(content)})
    summary = ("共扫描 %d 个赛事，%d 个存在资料缺口。" % (len([f for f in os.listdir(DATA_DIR) if f.endswith('.txt')]), len(gaps)))
    return {"gaps": gaps, "total": len(gaps), "summary": summary}
