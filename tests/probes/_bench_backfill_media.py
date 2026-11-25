# -*- coding: utf-8 -*-
"""给评测结果补回「富媒体是否产出」标记。

为什么需要：深度版会产图表/表格/路演PPT，但它们不在正文里。评测脚本早先只把正文
喂给自查，于是「缺图表」的扣分全算在深度版头上（实测 c11 -10.0、c14 -7.5 反被判低）。
正文 txt 里没有这个信息，但隔离库里存了每次生成的完整 result_data，可以按
「创意原文 + 档位」精确回填——不是猜，是取当次生成的记录。

用法：
    python tests/probes/_bench_backfill_media.py [run_dir]
默认读 benchmarks/.bench/current_run 指向的那一轮。
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BENCH_DIR = os.path.join(ROOT, "benchmarks")
DB = os.path.join(BENCH_DIR, ".bench", "bench.db")


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else open(
        os.path.join(BENCH_DIR, ".bench", "current_run")).read().strip()
    run_dir = run if os.path.isabs(run) else os.path.join(BENCH_DIR, "runs", run)
    cases = {c["id"]: c for c in json.load(
        open(os.path.join(BENCH_DIR, "cases.json"), encoding="utf-8"))["cases"]}

    conn = sqlite3.connect(DB)
    filled = 0
    for fn in sorted(os.listdir(run_dir)):
        if not fn.endswith(".meta.json"):
            continue
        case_id, _, arm = fn[:-len(".meta.json")].partition("_")
        if arm not in ("fast", "deep") or case_id not in cases:
            continue
        path = os.path.join(run_dir, fn)
        meta = json.load(open(path, encoding="utf-8"))
        if "rich_charts" in meta:
            continue
        row = conn.execute(
            "SELECT result_data FROM history WHERE idea=? AND mode=? ORDER BY id DESC LIMIT 1",
            (cases[case_id]["idea"], arm)).fetchone()
        if not row:
            print("  跳过（库里找不到）：%s %s" % (case_id, arm))
            continue
        rec = json.loads(row[0] or "{}")
        for k in ("rich_charts", "rich_tables", "rich_deck"):
            meta[k] = bool(rec.get(k))
        json.dump(meta, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        filled += 1
        print("  %s %s → 图表%s 表格%s PPT%s" % (
            case_id, arm, "有" if meta["rich_charts"] else "无",
            "有" if meta["rich_tables"] else "无", "有" if meta["rich_deck"] else "无"))
    conn.close()
    print("回填 %d 条" % filled)


if __name__ == "__main__":
    main()
