# -*- coding: utf-8 -*-
"""量化清理链对诊断分的影响：拿历史正文洗一遍，重新诊断，对比。

只读，不写库。在服务器上执行：
    cd /opt/comp-agent && .venv/bin/python /tmp/_probe_cleanup_gain.py
"""
import json
import sqlite3
import sys

sys.path.insert(0, "/opt/comp-agent")

import competition_agents as ca          # noqa: E402
from scorecard import diagnose           # noqa: E402

ORDER = (ca._strip_revision_note, ca._strip_pending_sections, ca._dedupe_consecutive,
         ca._strip_placeholders, ca._downgrade_fabrication, ca._strip_fabricated_times,
         ca._fix_mislabeled_measured, ca._strip_ai_artifacts, ca._strip_cliches)

FIELDS = ("proposal", "judge_feedback", "proposal_analysis", "tech_solution",
          "competitor_analysis", "business_model", "risk_analysis",
          "defense_questions", "ppt_outline", "speech_script")


def clean(text):
    for fn in ORDER:
        text = fn(text)
    return text


def main():
    conn = sqlite3.connect("/opt/comp-agent/competition.db")
    rows = conn.execute(
        "SELECT id, mode, competition_name, result_data FROM history "
        "ORDER BY id DESC LIMIT 60").fetchall()

    n = gap_before = gap_after = up = 0
    totals_b, totals_a = [], []
    for hid, mode, comp, data in rows:
        rec = json.loads(data or "{}")
        if not (rec.get("proposal") or "").strip():
            continue
        d1 = diagnose(rec, comp or "", None, mode or "fast")
        if not d1["available"]:
            continue
        rec2 = dict(rec)
        for k in FIELDS:
            if isinstance(rec2.get(k), str) and rec2[k]:
                rec2[k] = clean(rec2[k])
        d2 = diagnose(rec2, comp or "", None, mode or "fast")
        n += 1
        if any("非通用表述" in g["gap"] for g in d1["top_gaps"]):
            gap_before += 1
        if any("非通用表述" in g["gap"] for g in d2["top_gaps"]):
            gap_after += 1
        totals_b.append(d1["total"])
        totals_a.append(d2["total"])
        if d2["total"] > d1["total"]:
            up += 1

    print("可比记录 %d 条" % n)
    print("「非通用表述」进入 top_gaps 的记录: %d -> %d" % (gap_before, gap_after))
    print("自查均分: %.1f -> %.1f" % (sum(totals_b) / n, sum(totals_a) / n))
    print("分数上升的记录: %d / %d" % (up, n))


if __name__ == "__main__":
    main()
