# -*- coding: utf-8 -*-
"""数据洞察（确定性聚合，不调 LLM）：反馈需求优先级 + 评分维度诊断。"""
import json
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "competition.db")


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def feedback_priority(top_k=5):
    """按分类聚合用户反馈，给「最该修什么」排优先级。

    打分 = 数量权重 + 新近度权重（问题反馈/吐槽权重大于功能建议/好评）。
    返回 [{"category":..., "count":..., "latest":..., "priority":...}]
    """
    try:
        c = _conn()
        rows = c.execute(
            "SELECT category, content, created_time FROM feedback ORDER BY id DESC LIMIT 500"
        ).fetchall()
        c.close()
    except Exception:
        return []
    if not rows:
        return []

    _W = {"问题反馈": 4, "吐槽": 3, "功能建议": 2, "好评": 1, "其他": 1}
    agg = {}
    for r in rows:
        cat = r["category"] or "其他"
        d = agg.setdefault(cat, {"category": cat, "count": 0, "latest": "", "priority": 0})
        d["count"] += 1
        if not d["latest"]:
            d["latest"] = r["created_time"] or ""
    for cat, d in agg.items():
        # 数量为主，问题类加权；新近度只做轻微加成
        d["priority"] = round(d["count"] * _W.get(cat, 1) * 1.0, 1)
    ordered = sorted(agg.values(), key=lambda x: -x["priority"])
    return ordered[:top_k]


def feedback_priority_text():
    items = feedback_priority()
    if not items:
        return ""
    tops = items[:3]
    desc = "、".join("%s(%d条)" % (it["category"], it["count"]) for it in tops)
    return "近期用户反馈里，最需要优先处理的是：%s。" % desc


def score_diagnosis(min_samples=2):
    """聚合历史 judge_scores，找「平均分最低、最常被扣分」的维度。

    返回 {"dimensions":[...], "weak":[...], "diagnosis_text": "..."}
    """
    try:
        c = _conn()
        rows = c.execute(
            "SELECT result_data FROM history ORDER BY id DESC LIMIT 300").fetchall()
        c.close()
    except Exception:
        return {"dimensions": [], "weak": [], "diagnosis_text": ""}

    dims = {}
    for r in rows:
        try:
            d = json.loads(r["result_data"])
        except Exception:
            continue
        js = d.get("judge_scores") or []
        for it in js:
            if not isinstance(it, dict):
                continue
            name, sc = it.get("name"), it.get("score")
            if not name or sc is None:
                continue
            try:
                sc = float(sc)
            except (TypeError, ValueError):
                continue
            dims.setdefault(str(name), []).append(sc)

    agg = []
    for name, scores in dims.items():
        if len(scores) < min_samples:
            continue
        avg = sum(scores) / len(scores)
        low = sum(1 for s in scores if s < 70)
        agg.append({
            "name": name, "avg": round(avg, 1), "samples": len(scores),
            "low_rate": round(low / len(scores), 2),
        })
    agg.sort(key=lambda x: x["avg"])
    weak = [x for x in agg if x["avg"] < 75][:3]
    text = ""
    if weak:
        names = "、".join(x["name"] for x in weak)
        text = ("历史评委打分显示「%s」维度平均分偏低，写作时请重点补强这些维度："
                "补实测数据、补量化对比、补落地证据。" % names)
    return {"dimensions": agg, "weak": weak, "diagnosis_text": text}
