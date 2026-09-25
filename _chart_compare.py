# -*- coding: utf-8 -*-
"""图表升级前后对比：同一份真实数据，分别用旧/新渲染器出图。

产物：
    _verify_out/charts_before/chart_<id>.png   ← chart_renderer（旧）
    _verify_out/charts_after/chart_<id>.png    ← chart_renderer_pro（新）
    _verify_out/chart_compare_meta.json        ← 供 HTML 对比页读取
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_verify_out")
BEFORE = os.path.join(OUT, "charts_before")
AFTER = os.path.join(OUT, "charts_after")

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_h41.json")


def load_charts():
    """历史记录里 rich_charts[i]['spec'] 才是原始图表定义（含 type/data）。"""
    with open(SRC, encoding="utf-8") as f:
        d = json.load(f)
    r = d.get("data") or d
    out = []
    for x in (r.get("rich_charts") or []):
        spec = x.get("spec") if isinstance(x.get("spec"), dict) else x
        out.append(spec)
    return out


TYPE_CN = {
    "radar": "雷达图", "bar": "柱状图", "column": "柱状图", "line": "折线图",
    "pie": "饼图", "donut": "环形图", "timeline": "甘特图", "gantt": "甘特图",
    "architecture": "架构图", "arch": "架构图", "matrix": "象限图",
    "quadrant": "象限图", "funnel": "漏斗图",
}


def guess_type(ch):
    t = str(ch.get("type") or "").lower()
    if t in TYPE_CN:
        return TYPE_CN[t]
    data = ch.get("data") or {}
    if "layers" in data:
        return "架构图"
    if "stages" in data:
        return "甘特图"
    if "points" in data:
        return "象限图"
    if "series" in data:
        return "雷达图"
    if "categories" in data:
        return "柱状图"
    return "饼图"


def main():
    charts = load_charts()
    if not charts:
        print("没有图表数据，退出")
        return 1

    for p in (BEFORE, AFTER):
        shutil.rmtree(p, ignore_errors=True)
        os.makedirs(p, exist_ok=True)

    import chart_renderer as old
    import chart_renderer_pro as new

    meta = []
    for ch in charts:
        cid = str(ch.get("id") or "x")
        title = ch.get("title") or ""
        caption = ch.get("caption") or ""
        ctype = guess_type(ch)

        b = old.render(ch, BEFORE, theme="tech")
        a = new.render(ch, AFTER, theme="tech")

        bs = os.path.getsize(b) if b and os.path.exists(b) else 0
        as_ = os.path.getsize(a) if a and os.path.exists(a) else 0
        meta.append({
            "id": cid,
            "type": ctype,
            "title": title,
            "caption": caption,
            "before": os.path.basename(b) if b else "",
            "after": os.path.basename(a) if a else "",
            "before_kb": round(bs / 1024, 1),
            "after_kb": round(as_ / 1024, 1),
            "ok": bool(b and a),
        })
        flag = "OK " if (b and a) else "FAIL"
        print(f"{flag} {cid:3s} {ctype:5s} 旧 {bs/1024:6.1f}KB → 新 {as_/1024:6.1f}KB | {title[:30]}")

    with open(os.path.join(OUT, "chart_compare_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    ok = sum(1 for m in meta if m["ok"])
    print(f"\n完成：{ok}/{len(meta)} 组对比图已生成 → {OUT}")
    return 0 if ok == len(meta) else 2


if __name__ == "__main__":
    sys.exit(main())
