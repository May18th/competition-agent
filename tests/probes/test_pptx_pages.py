# -*- coding: utf-8 -*-
"""tmp_pptx_pagetest.py — pptx_builder 页数翻倍修复的前后对比验证（只读，不改项目文件）。

用云端真实 deep 记录 271 的 rich_deck（18 页大纲、要点长 17~142 字、多图表页）
分别用 git HEAD 旧版模块和修复后的新版模块构建 PPT，对比总页数；
另跑 3 个边界用例（表格续页预算 / 纯文字超容量 / 超 20 页 deck 的压缩保护）。
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PY = "C:/Users/34984/.workbuddy/binaries/python/versions/3.13.12/python.exe"
GEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def chart_paths_for(deck):
    """把 deck 引用到的图表 id 全部指到本地已有 PNG（页数测试只关心版式分页）。"""
    pngs = [os.path.join(GEN, f) for f in os.listdir(GEN) if f.endswith(".png")]
    ids = set()
    for s in deck.get("slides", []):
        if isinstance(s, dict) and s.get("chart"):
            ids.add(str(s["chart"]))
    return {i: pngs[k % len(pngs)] for k, i in enumerate(sorted(ids))}


def count_pages(path):
    from pptx import Presentation
    return len(Presentation(path).slides._sldIdLst)


def notes_dump(path, max_n=3):
    from pptx import Presentation
    prs = Presentation(path)
    out = []
    for idx, s in enumerate(prs.slides):
        if s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip():
            out.append((idx + 1, s.notes_slide.notes_text_frame.text.strip()[:80]))
    return out[:max_n], len(out)


def main():
    before = load_module(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "tmp_pptx_builder_before.py"), "pptx_before")
    import pptx_builder as after  # noqa: 修复后的新版

    results = []

    # ---- 用例 1：云端真实 deep 记录 271（18 slides / 大纲解析 19 页）----
    with open("tmp_deck271.json", encoding="utf-8") as f:
        payload = json.load(f)
    deck = payload["deck"]
    cp = chart_paths_for(deck)
    print(f"[用例1] 真实记录 271：{len(deck['slides'])} slides，chart_ids={sorted(cp)}")

    before.build_deck(dict(deck), "tmp_before_271.pptx", cp)
    after.build_deck(dict(deck), "tmp_after_271.pptx", cp)
    nb, na = count_pages("tmp_before_271.pptx"), count_pages("tmp_after_271.pptx")
    results.append(("真实记录271(大纲19页)", nb, na))
    dump, total_notes = notes_dump("tmp_after_271.pptx")
    print(f"  旧版 {nb} 页 -> 新版 {na} 页；新版含备注页数 {total_notes}")
    for pg, txt in dump:
        print(f"    第{pg}页备注: {txt}")

    # ---- 用例 2：表格 20 行（>MAX_TABLE_ROWS_PER_SLIDE=7）在 6 页小 deck ----
    tbl_deck = {"project": "表格测试", "one_liner": "", "competition": "",
                "theme": "star", "slides": [
                    {"type": "cover", "title": "T"},
                    {"type": "table", "title": "大表",
                     "table": {"header": ["A", "B", "C"],
                               "rows": [[str(i), str(i * 2), str(i * 3)] for i in range(20)]}},
                    {"type": "bullets", "title": "尾页", "bullets": ["x"]},
                ]}
    before.build_deck(json.loads(json.dumps(tbl_deck)), "tmp_before_tbl.pptx", {})
    after.build_deck(json.loads(json.dumps(tbl_deck)), "tmp_after_tbl.pptx", {})
    results.append(("20行表格(6页deck,预算14)", count_pages("tmp_before_tbl.pptx"),
                    count_pages("tmp_after_tbl.pptx")))

    # ---- 用例 3：纯文字页 12 条要点（>MAX_BLOCKS_PER_SLIDE=8），deck 19 页（预算 1）----
    _slides3 = [{"type": "cover", "title": "T"},
                {"type": "bullets", "title": "十二要点页",
                 "bullets": [("要点%02d：" % i) + "内容" * 10 for i in range(12)]}]
    _slides3 += [{"type": "bullets", "title": "普通页%d" % i, "bullets": ["a", "b"]}
                 for i in range(17)]
    big_deck = {"project": "预算测试", "one_liner": "", "competition": "",
                "theme": "star", "slides": _slides3}
    before.build_deck(json.loads(json.dumps(big_deck)), "tmp_before_big.pptx", {})
    after.build_deck(json.loads(json.dumps(big_deck)), "tmp_after_big.pptx", {})
    results.append(("12要点页+18普通页(19页deck,预算1)",
                    count_pages("tmp_before_big.pptx"), count_pages("tmp_after_big.pptx")))

    # ---- 用例 4：25 页 deck（基础页数已超 MAX_TOTAL_SLIDES，预算 0）----
    _slides4 = [{"type": "cover", "title": "T"},
                {"type": "bullets", "title": "十要点页",
                 "bullets": [("要点%02d：" % i) + "内容" * 10 for i in range(10)]}]
    _slides4 += [{"type": "bullets", "title": "普通页%d" % i, "bullets": ["a", "b"]}
                 for i in range(23)]
    over_deck = {"project": "超限测试", "one_liner": "", "competition": "",
                 "theme": "star", "slides": _slides4}
    after.build_deck(json.loads(json.dumps(over_deck)), "tmp_after_over.pptx", {})
    results.append(("25页deck含10要点页(预算0)", "-", count_pages("tmp_after_over.pptx")))

    print("\n==== 页数对比汇总 ====")
    for name, nb, na in results:
        verdict = ""
        if isinstance(na, int) and name.startswith("真实"):
            verdict = "（目标 ≤19）" + ("达标 ✓" if na <= 19 else "未达标 ✗")
        if "超限" in name:
            verdict = "（目标 ≤25=章节数，无续页）" + ("达标 ✓" if na <= 25 else "未达标 ✗")
        print(f"  {name}: 旧版 {nb} 页 -> 新版 {na} 页 {verdict}")


if __name__ == "__main__":
    main()
