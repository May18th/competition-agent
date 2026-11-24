# -*- coding: utf-8 -*-
"""批量复评：对历史正文跑「清理前 vs 清理后」的导出评分，量化清理链的效果。

输入（stdin，JSON Lines，每行一条）：
    {"id": 319, "mode": "deep", "proposal": "..."}

配套取数（在线上服务器跑，导出最近 N 条历史正文）：
    ssh root@host "cd /opt/comp-agent && python3 -c \"import sqlite3,json;c=sqlite3.connect('competition.db');[print(json.dumps({'id':i,'mode':m,'proposal':(json.loads(d) or {}).get('proposal','')},ensure_ascii=False)) for i,m,d in c.execute('select id,mode,result_data from history order by id desc limit 30')]\"" | python tests/probes/_probe_cliche_batch.py

只统计、不落盘：正文只在内存里过一遍。
"""
import json
import sys

sys.path.insert(0, ".")
from backend.competition_agents import (_dedupe_consecutive, _strip_placeholders,
                                        _downgrade_fabrication, _strip_fabricated_times,
                                        _fix_mislabeled_measured, _strip_ai_artifacts,
                                        _strip_cliches)
from backend.quality_gate import score_export

CLICHE = ("进一步提升", "不断完善", "积极探索", "高度重视", "显著提高",
          "赋能", "闭环", "抓手", "扎实推进", "深入贯彻")


def clean(text):
    return _strip_cliches(_strip_ai_artifacts(_fix_mislabeled_measured(
        _strip_fabricated_times(_downgrade_fabrication(
            _strip_placeholders(_dedupe_consecutive(text)))))))


def _score(proposal, mode):
    rec = {"proposal": proposal, "completeness": {"missing": []}}
    out = score_export(rec, mode)
    score, reasons = out[0], out[2]
    return score, reasons


def main():
    rows = [json.loads(line) for line in sys.stdin if line.strip()]
    if not rows:
        print("stdin 为空：先用 ssh 导出历史正文")
        return 1

    before_hit = {"套话": 0, "占位符": 0, "分数": 0}
    after_hit = {"套话": 0, "占位符": 0, "分数": 0}
    detail = []
    for r in rows:
        p = r.get("proposal") or ""
        if not p.strip():
            continue
        mode = "deep" if str(r.get("mode", "")).strip().lower() == "deep" else "fast"
        s1, re1 = _score(p, mode)
        s2, re2 = _score(clean(p), mode)
        b1 = sum(1 for c in CLICHE if c in p)
        b2 = sum(1 for c in CLICHE if c in clean(p))
        p1 = 1 if any("占位符" in x for x in re1) else 0
        p2 = 1 if any("占位符" in x for x in re2) else 0
        before_hit["套话"] += b1
        before_hit["占位符"] += p1
        before_hit["分数"] += s1
        after_hit["套话"] += b2
        after_hit["占位符"] += p2
        after_hit["分数"] += s2
        detail.append((r.get("id"), mode, b1, b2, p1, p2, s1, s2, re2))

    n = len(detail)
    print("样本 %d 条" % n)
    print("套话命中（处）: %d -> %d" % (before_hit["套话"], after_hit["套话"]))
    print("占位符命中（条）: %d -> %d" % (before_hit["占位符"], after_hit["占位符"]))
    print("平均分: %.1f -> %.1f" % (before_hit["分数"] / n, after_hit["分数"] / n))
    changed = [d for d in detail if d[2] != d[3] or d[4] != d[5] or d[6] != d[7]]
    print("有变化的记录 %d 条：" % len(changed))
    for hid, mode, b1, b2, p1, p2, s1, s2, re2 in changed[:12]:
        flag = ""
        if s2 == 0 and s1 > 0:
            flag = "  ← 清理后触发否决: " + "；".join(re2[:2])
        print("  hid=%-4s %-4s 套话 %d->%d 占位符 %d->%d 分数 %s->%s%s" % (
            hid, mode, b1, b2, p1, p2, s1, s2, flag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
