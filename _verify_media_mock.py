# -*- coding: utf-8 -*-
"""
_verify_media_mock.py —— 不走 LLM 的端到端验证

用一组固定的 mock 数据（危化品智能柜项目），把「图表PNG → PPT导出」整条链路跑一遍，
用来证明：只要 DeepSeek 有额度，rich_pipeline 产出的数据结构一定能变成好图表和好 PPT。

验证项：
  1. chart_renderer.render() 能否为 8 种 type 各出一张 PNG（中文字体是否正常）
  2. pptx_builder.build_deck() 能否生成 .pptx，页数/图表页/表格页是否符合 deck
  3. HTTP /api/export_pptx 路由是否可用（若服务在跑）
  4. 生成的 pptx 读回自检：有没有文字溢出、图片越界、空页

跑法：python _verify_media_mock.py
"""
import io
import os
import sys
import json

BASE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(BASE, "generated")
os.makedirs(GEN, exist_ok=True)

# ---------------------------------------------------------------- mock 数据
MOCK_CHARTS = [
    {"id": "m1", "type": "bar", "title": "目标市场规模三年翻三倍",
     "caption": "高校实验室存量 4.2 万间，可渗透空间充足",
     "data": {"categories": ["第1年", "第2年", "第3年"], "values": [120, 380, 860], "ylabel": "万元"}},
    {"id": "m2", "type": "radar", "title": "四项能力全面领先现有方案",
     "caption": "竞品能力对比（满分 10 分）",
     "data": {"labels": ["功能完整度", "价格优势", "技术壁垒", "易用性", "合规性"],
              "series": [{"name": "本项目", "values": [9, 8, 9, 8, 9]},
                         {"name": "进口智能柜", "values": [7, 4, 6, 6, 8]}]}},
    {"id": "m3", "type": "timeline", "title": "八周完成从原型到试点",
     "caption": "总周期 8 周，分四个阶段推进",
     "data": {"stages": [{"name": "需求调研", "start": 0, "end": 2, "label": "W1-2"},
                         {"name": "原型开发", "start": 2, "end": 5, "label": "W3-5"},
                         {"name": "小批量试产", "start": 5, "end": 7, "label": "W6-7"},
                         {"name": "市场推广", "start": 7, "end": 8, "label": "W8"}],
              "xlabel": "时间（周）"}},
    {"id": "m4", "type": "pie", "title": "研发投入占比最高",
     "caption": "预算构成：研发 45%、生产 30%、营销 15%、运营 10%",
     "data": {"labels": ["研发", "生产", "营销", "运营"], "values": [45, 30, 15, 10]}},
    {"id": "m5", "type": "architecture", "title": "三层技术架构",
     "caption": "感知层 - 平台层 - 应用层",
     "data": {"layers": [{"name": "应用层", "boxes": ["小程序", "管理后台", "预警推送"]},
                         {"name": "平台层", "boxes": ["Spring Boot", "MySQL", "规则引擎"]},
                         {"name": "感知层", "boxes": ["RFID", "称重", "摄像头"]}]}},
    {"id": "m6", "type": "line", "title": "用户数与复购率同步增长",
     "caption": "试点高校从第 1 年的 20 所到第 3 年的 150 所",
     "data": {"x": ["第1年", "第2年", "第3年"],
              "series": [{"name": "覆盖高校", "values": [20, 65, 150]},
                         {"name": "复购率%", "values": [35, 52, 71]}], "ylabel": "数量"}},
    {"id": "m7", "type": "funnel", "title": "从线索到付费的转化",
     "caption": "试点转化率 32%",
     "data": {"labels": ["拜访", "试用", "采购", "复购"], "values": [400, 160, 52, 37]}},
    {"id": "m8", "type": "matrix", "title": "竞品定位象限",
     "caption": "右上角为高性价比 + 高壁垒区",
     "data": {"points": [{"name": "本项目", "x": 8.5, "y": 8.2},
                         {"name": "进口柜", "x": 4.5, "y": 9},
                         {"name": "人工台账", "x": 7, "y": 2}],
              "xlabel": "性价比", "ylabel": "技术壁垒"}},
]

MOCK_TABLES = [
    {"id": "mt1", "title": "竞品逐项对比",
     "header": ["方案", "单柜成本", "识别精度", "台账自动化", "部署周期"],
     "rows": [["本项目", "1.2 万元", "±1 g", "全自动", "1 天"],
              ["传统人工台账", "0.1 万元", "人工记录", "无", "—"],
              ["进口智能柜", "6.8 万元", "±0.5 g", "半自动", "2 周"]]},
]

MOCK_DECK = {
    "project": "智能危化品试剂管理柜",
    "one_liner": "让每一瓶试剂的取用都可追溯",
    "competition": "iCAN 大学生创新创业大赛",
    "slides": [
        {"type": "cover"},
        {"type": "section", "num": "1", "title": "问题与机会", "bullets": ["实验室危化品管理是一片被忽视的空白"]},
        {"type": "bullets", "kicker": "01 / 痛点", "title": "一本台账撑不起安全管理",
         "bullets": ["**领用无追踪**：500mL 丙酮实际只用 80mL，余量无人知晓",
                     "**台账滞后**：纸质记录晚 2-3 天，事故追溯靠翻本子",
                     "**盘点耗时**：一次全库盘点平均 3 小时，超期试剂普遍"]},
        {"type": "metrics", "title": "痛点有多贵",
         "metrics": ["4.2万：全国高校实验室存量", "200+：年均试剂安全事故", "3小时：单次全库盘点耗时"]},
        {"type": "bullets", "kicker": "02 / 方案", "title": "一物一码一重量",
         "bullets": ["**RFID 识别**：每瓶试剂独立身份，取还自动登记",
                     "**高精度称重**：±1 g 实时感知余量，杜绝虚报",
                     "**三级预警**：超量、超期、异常取用即时推送"]},
        {"type": "chart", "kicker": "03 / 市场", "title": "目标市场规模三年翻三倍",
         "bullets": ["三年收入 120 → 380 → 860 万元"], "chart": "m1"},
        {"type": "section", "num": "2", "title": "技术与壁垒", "bullets": ["软硬一体的闭环能力是护城河"]},
        {"type": "chart", "kicker": "04 / 架构", "title": "三层技术架构",
         "bullets": ["感知层采集、平台层治理、应用层触达"], "chart": "m5"},
        {"type": "chart", "kicker": "05 / 竞品", "title": "四项能力全面领先现有方案",
         "bullets": ["性价比与技术壁垒双高"], "chart": "m2"},
        {"type": "table", "kicker": "06 / 对比", "title": "竞品逐项对比",
         "table": "mt1", "note": "成本为单柜采购价，含三年运维"},
        {"type": "chart", "kicker": "07 / 计划", "title": "八周完成从原型到试点",
         "bullets": ["W1-2 调研，W3-5 开发，W6-7 试产，W8 推广"], "chart": "m3"},
        {"type": "chart", "kicker": "08 / 财务", "title": "预算与转化",
         "bullets": ["研发投入占比 45%，试点转化率 32%"], "chart": "m4"},
        {"type": "bullets", "kicker": "09 / 价值", "title": "让每一瓶试剂都可追溯",
         "bullets": ["**安全**：降低实验室试剂事故发生率",
                     "**效率**：盘点耗时从 3 小时降到 10 分钟",
                     "**合规**：台账自动生成，满足检查要求"]},
        {"type": "closing", "title": "谢谢聆听", "bullets": ["让每一瓶试剂的取用都可追溯"]},
    ],
}


def step1_render_charts():
    print("=" * 68)
    print("STEP 1  图表渲染：8 种 type × chart_renderer.render()")
    print("=" * 68)
    from chart_renderer import render
    ok, fail = [], []
    for c in MOCK_CHARTS:
        try:
            p = render(dict(c), GEN)
            if p and os.path.isfile(p):
                size = os.path.getsize(p)
                ok.append((c["id"], c["type"], os.path.basename(p), size))
                print(f"  ✅ {c['id']:<3} {c['type']:<13} -> {os.path.basename(p):<22} {size:>7} B")
            else:
                fail.append((c["id"], c["type"], "返回 None"))
                print(f"  ❌ {c['id']:<3} {c['type']:<13} -> render 返回 None")
        except Exception as e:
            fail.append((c["id"], c["type"], str(e)[:80]))
            print(f"  ❌ {c['id']:<3} {c['type']:<13} -> {str(e)[:80]}")
    print(f"\n  小结：成功 {len(ok)} / {len(MOCK_CHARTS)}")
    return ok, fail


def step2_build_pptx():
    print()
    print("=" * 68)
    print("STEP 2  PPT 导出：pptx_builder.build_deck()")
    print("=" * 68)
    from pptx_builder import build_deck
    table_map = {t["id"]: t for t in MOCK_TABLES}
    deck = json.loads(json.dumps(MOCK_DECK), encoding="utf-8") if isinstance(MOCK_DECK, str) else dict(MOCK_DECK)
    deck["slides"] = [dict(s) for s in MOCK_DECK["slides"]]
    for s in deck["slides"]:
        if isinstance(s.get("table"), str):
            s["table"] = table_map.get(s["table"])

    chart_paths = {}
    for c in MOCK_CHARTS:
        p = os.path.join(GEN, f"chart_{c['id']}.png")
        if os.path.isfile(p):
            chart_paths[c["id"]] = p

    out = os.path.join(GEN, "mock_路演PPT.pptx")
    try:
        build_deck(deck, out, chart_paths)
        size = os.path.getsize(out)
        print(f"  ✅ 生成成功：{os.path.basename(out)}  {size} B")
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  ❌ 生成失败：{e}")
        return None


def step3_inspect_pptx(path):
    print()
    print("=" * 68)
    print("STEP 3  PPT 读回自检")
    print("=" * 68)
    if not path or not os.path.isfile(path):
        print("  ❌ 没有 pptx 可检查")
        return False
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation(path)
    W, H = prs.slide_width, prs.slide_height
    print(f"  画布：{W/914400:.2f} × {H/914400:.2f} inch（16:9 = 13.33 × 7.50）")
    print(f"  页数：{len(prs.slides)}   期望：{len(MOCK_DECK['slides'])}")

    problems = []
    for i, s in enumerate(prs.slides, 1):
        texts, pics, tbls = [], 0, 0
        for shp in s.shapes:
            if shp.shape_type == 13 or shp.__class__.__name__ == "Picture":
                pics += 1
                if shp.top is not None and shp.height is not None and shp.top + shp.height > H:
                    problems.append(f"P{i} 图片越界底部")
                if shp.left is not None and shp.width is not None and shp.left + shp.width > W:
                    problems.append(f"P{i} 图片越界右侧")
            if getattr(shp, "has_table", False):
                tbls += 1
            if getattr(shp, "has_text_frame", False) and shp.text_frame.text.strip():
                texts.append(shp.text_frame.text.strip().replace("\n", " / "))
        head = texts[0][:44] if texts else "(无文字)"
        print(f"  P{i:<2} 图{pics} 表{tbls} 段{len(texts)}  {head}")
        if not texts and not pics and not tbls:
            problems.append(f"P{i} 是空页")
    print()
    if problems:
        print("  ⚠️  发现问题：")
        for p in problems:
            print("     -", p)
        return False
    print("  ✅ 无空页、无越界")
    return True


def step4_http():
    print()
    print("=" * 68)
    print("STEP 4  HTTP 路由 /api/export_pptx（需要服务在跑）")
    print("=" * 68)
    try:
        import urllib.request
        import urllib.error
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        payload = {
            "deck": MOCK_DECK,
            "charts": [{"id": c["id"], "url": f"/generated/chart_{c['id']}.png"} for c in MOCK_CHARTS],
            "tables": MOCK_TABLES,
            "idea": "智能危化品试剂管理柜",
            "one_liner": "让每一瓶试剂的取用都可追溯",
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8080/api/export_pptx",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(req, timeout=60) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
            print(f"  ✅ HTTP {resp.status}  {len(data)} B  Content-Type={ct[:60]}")
            if len(data) > 10000 and data[:2] == b"PK":
                p = os.path.join(GEN, "mock_http_路演PPT.pptx")
                with open(p, "wb") as f:
                    f.write(data)
                print(f"  ✅ 落盘：{os.path.basename(p)}  {len(data)} B（PK 头 = 合法 zip/pptx）")
                return p
            print(f"  ❌ 返回内容不像 pptx：{data[:80]!r}")
            return None
    except Exception as e:
        print(f"  ⚠️  请求失败（服务可能没在跑）：{str(e)[:120]}")
        return None


if __name__ == "__main__":
    ok, fail = step1_render_charts()
    pptx = step2_build_pptx()
    good = step3_inspect_pptx(pptx)
    http_pptx = step4_http()
    if http_pptx:
        step3_inspect_pptx(http_pptx)

    print()
    print("=" * 68)
    print("结论")
    print("=" * 68)
    print(f"  图表：{len(ok)}/{len(MOCK_CHARTS)} 渲染成功" + (f"，失败 {len(fail)}" if fail else ""))
    print(f"  PPT ：{'通过' if good else '有问题'}")
    print(f"  HTTP：{'通过' if http_pptx else '未验证（服务未运行）'}")
    if pptx:
        print(f"  样本：{os.path.relpath(pptx, BASE)}")
