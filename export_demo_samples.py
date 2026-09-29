# -*- coding: utf-8 -*-
"""309 轮：从历史记录导出「一键演示」样例数据。

从 competition.db 挑出「深度版 + 完整富媒体（proposal + rich_charts/rich_tables/rich_deck）」的记录，
按赛事去重（多样性优先），导出为：
  - demo_sample.json / demo_sample2.json / ...  （仓库根，纯 result_data dict，供后端 /api/demo 读取）
  - static/demo_sample.json                       （{success, data} 包装，供前端 app.js 一键演示读取）

用法（在服务器 /opt/comp-agent 下跑）：
  .venv/bin/python export_demo_samples.py [数量，默认 5]

注意：本地沙箱无 LLM，脚本只做「从已有历史挑样例」，不新生成内容。
"""
import json
import os
import sqlite3
import sys


# 339/341 轮：剔除「网站自身功能/产品名自述」的样例——这些不是参赛学生项目内容。
# 只保留强自述信号（产品名/网站专属功能），不放 Milvus/Neo4j 这类可被真实项目合法使用的技术名词。
_SELF_REF_KEYWORDS = (
    "创科智绘", "科创智绘", "科创赛事助手", "评审引擎", "多智能体", "智能体节点",
    "双盲脱敏", "去AI味", "去 AI 味", "获奖范文库", "流式输出",
    "规则打分", "模型打分", "人工校准", "186份人工标注",
)


def main():
    n = 5
    if len(sys.argv) > 1:
        try:
            n = max(1, int(sys.argv[1]))
        except ValueError:
            pass

    base = os.path.dirname(os.path.abspath(__file__))
    db = os.path.join(base, "competition.db")
    if not os.path.isfile(db):
        print("未找到 competition.db：", db)
        sys.exit(1)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, competition_name, result_data FROM history "
        "WHERE mode='deep' ORDER BY id DESC").fetchall()
    conn.close()

    seen_comp = set()
    picked = []
    skipped_selfref = 0
    for r in rows:
        try:
            data = json.loads(r["result_data"])
        except Exception:
            continue
        # 完整样例：有正文 + 至少一种富媒体（图表/表格/PPT）
        if not data.get("proposal"):
            continue
        if not (data.get("rich_charts") or data.get("rich_tables") or data.get("rich_deck")):
            continue
        # 339/341 轮：正文/创意里出现网站自身功能描述 → 跳过（防「用网站介绍冒充作品正文」）
        _blob = json.dumps(data, ensure_ascii=False)
        if any(k in _blob for k in _SELF_REF_KEYWORDS):
            skipped_selfref += 1
            continue
        comp = (r["competition_name"] or "").strip() or "未指定赛事"
        if comp in seen_comp:
            continue  # 多样性优先：同一赛事只取一条（最新）
        seen_comp.add(comp)
        picked.append((r["id"], comp, data))
        if len(picked) >= n:
            break

    if not picked:
        print("没有可导出的完整深度版记录（需 mode=deep 且含 proposal + rich 富媒体，且不含网站自述）")
        sys.exit(1)

    if skipped_selfref:
        print("已跳过 %d 条含「网站自身功能自述」的样例" % skipped_selfref)

    for i, (hid, comp, data) in enumerate(picked):
        fname = "demo_sample.json" if i == 0 else "demo_sample%d.json" % (i + 1)
        path = os.path.join(base, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        size = os.path.getsize(path)
        print("[%d] id=%s %s -> %s (%dB)" % (i + 1, hid, comp, fname, size))

    # 前端 static/demo_sample.json：{success, data} 包装，取第一条
    static_dir = os.path.join(base, "static")
    os.makedirs(static_dir, exist_ok=True)
    static_path = os.path.join(static_dir, "demo_sample.json")
    with open(static_path, "w", encoding="utf-8") as f:
        json.dump({"success": True, "data": picked[0][2]}, f, ensure_ascii=False)
    print("static/demo_sample.json (%dB, success=True + data)" % os.path.getsize(static_path))

    print("\n共导出 %d 个样例。" % len(picked))


if __name__ == "__main__":
    main()
