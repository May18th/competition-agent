# -*- coding: utf-8 -*-
"""范文「写作范式蒸馏」：把范文库共性规律提炼成一段紧凑参考，注入生成 prompt。

与 kb_retrieve 的区别：
  - kb_retrieve：按关键词/模块检索具体范文原文，给「对标写法」；
  - kb_distill：给全体范文提炼出的「共性规律」，让主笔先对齐获奖范式再动笔。
读不到种子文件时静默返回空串，绝不阻断生成。
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "writing_paradigm.json")


def _load():
    try:
        with open(PARADIGM_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def paradigm_ref(module_tag=None, max_global=6):
    """返回一段可注入的「写作范式」文本；module_tag 给定则附带该模块的专门要点。"""
    p = _load()
    if not p:
        return ""
    parts = []
    g = p.get("global") or []
    if g:
        lines = ["（%d）%s" % (i + 1, s) for i, s in enumerate(g[:max_global])]
        parts.append("【写作范式（从真实获奖范文蒸馏，务必内化到写作里，不要照抄）】\n" + "\n".join(lines))
    if module_tag:
        mod = (p.get("modules") or {}).get(module_tag)
        if mod:
            parts.append("【本章写法要点】" + mod)
    return "\n\n".join(parts)
